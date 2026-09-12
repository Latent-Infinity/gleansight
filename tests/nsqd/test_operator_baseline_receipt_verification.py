from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

import nsqd.domain.operator_baselines as opb

CANDIDATE_HASH = hashlib.sha256(b"candidate-1").hexdigest()
CARD_HASH = hashlib.sha256(b"card-1").hexdigest()


@dataclass(frozen=True, slots=True)
class ReceiptFixture:
    scratch: Path
    db_path: Path
    index_path: Path
    receipt: dict[str, Any]
    scratch_runtime: dict[str, Any]
    candidate_payload: dict[str, Any]
    card_payload: dict[str, Any]


@pytest.fixture
def receipt_fixture(tmp_path: Path) -> Iterator[ReceiptFixture]:
    scratch = tmp_path / "nsqd-jepa-baselines-receipt"
    scratch.mkdir()
    db_path = scratch / "nsqd.sqlite"
    index_path = scratch / "index"
    index_path.mkdir()
    (index_path / "records.lance").write_bytes(b"deterministic-index")
    candidate_payload = {"candidate": {"title": "candidate-1"}, "operator": "A"}
    card_payload = {"card_id": CARD_HASH, "title": "candidate-1"}
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE nsqd_candidates "
            "(artifact_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE nsqd_frontier_cards "
            "(card_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
            (CANDIDATE_HASH, json.dumps(candidate_payload, sort_keys=True)),
        )
        connection.execute(
            "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) VALUES (?, ?, ?)",
            (CARD_HASH, "cell-1", json.dumps(card_payload, sort_keys=True)),
        )
    receipt = {
        "sqlite_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "lancedb_tree_sha256": opb.lancedb_tree_digest(index_path),
        "candidate_count": 1,
        "card_count": 1,
        "candidate_artifact_hashes": [CANDIDATE_HASH],
        "frontier_card_hashes": [CARD_HASH],
        "candidate_payload_sha256": {
            CANDIDATE_HASH: opb._canonical_payload_sha256(candidate_payload)
        },
        "frontier_card_payload_sha256": {CARD_HASH: opb._canonical_payload_sha256(card_payload)},
    }
    scratch_runtime = {
        "db_path": str(db_path),
        "index_path": str(index_path),
        "no_production_writes": True,
        "production_write_paths": [],
    }
    yield ReceiptFixture(
        scratch=scratch,
        db_path=db_path,
        index_path=index_path,
        receipt=receipt,
        scratch_runtime=scratch_runtime,
        candidate_payload=candidate_payload,
        card_payload=card_payload,
    )
    shutil.rmtree(scratch)
    assert not scratch.exists()


def test_actual_receipt_verification_binds_fixture_bytes_counts_identities_and_payloads(
    receipt_fixture: ReceiptFixture,
) -> None:
    runtime = opb.verify_scratch_execution_receipt(
        receipt_fixture.receipt,
        scratch_runtime=receipt_fixture.scratch_runtime,
    )

    assert (
        receipt_fixture.receipt["sqlite_sha256"]
        == hashlib.sha256(receipt_fixture.db_path.read_bytes()).hexdigest()
    )
    assert receipt_fixture.receipt["lancedb_tree_sha256"] == opb.lancedb_tree_digest(
        receipt_fixture.index_path
    )
    assert receipt_fixture.receipt["candidate_count"] == len(runtime["candidate_payloads"])
    assert receipt_fixture.receipt["card_count"] == len(runtime["frontier_card_payloads"])
    assert list(runtime["candidate_payloads"]) == [CANDIDATE_HASH]
    assert list(runtime["frontier_card_payloads"]) == [CARD_HASH]
    assert runtime["candidate_payloads"][CANDIDATE_HASH] == receipt_fixture.candidate_payload
    assert runtime["frontier_card_payloads"][CARD_HASH] == receipt_fixture.card_payload


@pytest.mark.parametrize(
    ("path", "value", "message"),
    (
        (("sqlite_sha256",), "0" * 64, "sqlite_sha256"),
        (("lancedb_tree_sha256",), "0" * 64, "lancedb_tree_sha256"),
        (("candidate_count",), 0, "candidate_count"),
        (
            ("frontier_card_payload_sha256", CARD_HASH),
            "0" * 64,
            "frontier card payload sha",
        ),
    ),
)
def test_actual_receipt_verification_rejects_fixture_tampering(
    receipt_fixture: ReceiptFixture,
    path: tuple[str, ...],
    value: str | int,
    message: str,
) -> None:
    tampered = copy.deepcopy(receipt_fixture.receipt)
    target = tampered
    for part in path[:-1]:
        target = cast(dict[str, Any], target[part])
    target[path[-1]] = value

    with pytest.raises(ValueError, match=message):
        opb.verify_scratch_execution_receipt(
            tampered,
            scratch_runtime=receipt_fixture.scratch_runtime,
        )
