from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import pytest

from tests.nsqd.operator_c_resolution_support import (
    ARTIFACT_NAMES,
    validate_resolution_manifest,
    validate_resolution_packet,
    validate_resolution_semantics,
)
from tests.nsqd.operator_c_resolution_test_support import (
    PACKET_ROOT,
    TAMPER_CASES,
    TamperCase,
    _tampered_packet,
)

REHASHED_TAMPER_CASES: Final = (
    TamperCase(
        "retrieval_uri",
        "bibliographic-query-receipts.json",
        ("query_batches", 1, "records", 0, "retrieval_uri"),
        "https://example.invalid/query",
        "resolution.query.request_uri.exact",
    ),
    TamperCase(
        "final_url",
        "bibliographic-query-receipts.json",
        ("query_batches", 1, "records", 0, "final_url"),
        "https://example.invalid/final",
        "resolution.query.final_url.exact",
    ),
    TamperCase(
        "batch_purpose",
        "bibliographic-query-receipts.json",
        ("query_batches", 1, "purpose"),
        "substituted purpose",
        "resolution.query.batch_identity.exact",
    ),
    TamperCase(
        "control_identity",
        "bibliographic-query-receipts.json",
        ("query_batches", 1, "control"),
        "sha256_seeded_shuffled_literature_pair_control_under_identical_query_budget",
        "resolution.query.batch_identity.exact",
    ),
    TamperCase(
        "interaction_count",
        "evidence-ledger.json",
        ("interaction_checks", 0, "observed_count"),
        999,
        "resolution.ledger.interaction_binding.exact",
    ),
    TamperCase(
        "interaction_query_binding",
        "evidence-ledger.json",
        ("interaction_checks", 0, "query_receipt_ids"),
        ["openalex-shuffled-1"],
        "resolution.ledger.interaction_binding.exact",
    ),
    TamperCase(
        "evidence_sufficient",
        "evidence-ledger.json",
        ("evidence_sufficient",),
        True,
        "resolution.ledger.evidence_sufficient.false",
    ),
    TamperCase(
        "protocol_path",
        "acquisition-receipts.json",
        ("protocol_path",),
        "../forged/protocol.json",
        "resolution.protocol.path.frozen",
    ),
    TamperCase(
        "protocol_digest",
        "evidence-ledger.json",
        ("protocol_packet_digest",),
        "0" * 64,
        "resolution.protocol.digest.frozen",
    ),
    TamperCase(
        "authorization_state",
        "evidence-ledger.json",
        ("authorization_state",),
        "runtime_authorized",
        "resolution.ledger.authorization.report_only",
    ),
    TamperCase(
        "source_scope",
        "evidence-ledger.json",
        ("source_scope",),
        "approved_corpus",
        "resolution.ledger.source_scope.exact",
    ),
    TamperCase(
        "full_text_inspected",
        "evidence-ledger.json",
        ("full_text_inspected",),
        False,
        "resolution.ledger.full_text.true",
    ),
    TamperCase(
        "result",
        "evidence-ledger.json",
        ("result",),
        "accepted",
        "resolution.ledger.result.insufficient",
    ),
    TamperCase(
        "operator_c_status",
        "evidence-ledger.json",
        ("operator_c_status",),
        "enabled",
        "resolution.ledger.operator_c.blocked",
    ),
    TamperCase(
        "operator_d_status",
        "evidence-ledger.json",
        ("operator_d_status",),
        "enabled",
        "resolution.ledger.operator_d.blocked",
    ),
    TamperCase(
        "schema_authority",
        "evidence-ledger.json",
        ("schema_admission_authorized",),
        True,
        "resolution.ledger.schema.false",
    ),
    TamperCase(
        "runtime_authority",
        "evidence-ledger.json",
        ("runtime_authorized",),
        True,
        "resolution.ledger.runtime.false",
    ),
    TamperCase(
        "universal_absence",
        "evidence-ledger.json",
        ("universal_absence_claimed",),
        True,
        "resolution.ledger.universal_absence.false",
    ),
    *(
        TamperCase(
            f"extract_{index}_section",
            "source-extracts.jsonl",
            (index, "section"),
            "Forged section",
            "resolution.extract.section.exact",
        )
        for index in range(9)
    ),
    *(
        TamperCase(
            f"extract_{index}_location",
            "source-extracts.jsonl",
            (index, "source_location"),
            "forged location",
            "resolution.extract.source_location.exact",
        )
        for index in range(9)
    ),
)


def test_resolution_packet_is_closed_and_valid() -> None:
    digest = validate_resolution_packet(PACKET_ROOT)
    assert {path.name for path in PACKET_ROOT.iterdir()} == ARTIFACT_NAMES
    assert len(digest) == 64


@pytest.mark.parametrize("case", TAMPER_CASES, ids=lambda case: case.name)
def test_resolution_semantics_fail_closed_when_tampered(tmp_path: Path, case: TamperCase) -> None:
    packet = _tampered_packet(tmp_path, case)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_resolution_semantics(packet)


@pytest.mark.parametrize("case", REHASHED_TAMPER_CASES, ids=lambda case: case.name)
def test_rehashed_semantic_corruptions_fail_closed(tmp_path: Path, case: TamperCase) -> None:
    packet = _tampered_packet(tmp_path, case, rehash=True)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_resolution_packet(packet)


def test_resolution_manifest_rejects_digest_tamper(tmp_path: Path) -> None:
    packet = tmp_path / "digest-tamper"
    shutil.copytree(PACKET_ROOT, packet)
    ledger = packet / "evidence-ledger.json"
    ledger.write_bytes(ledger.read_bytes() + b"\n")
    with pytest.raises(
        AssertionError, match="^resolution.manifest.artifact_sha256.match:evidence-ledger.json$"
    ):
        validate_resolution_manifest(packet)


def test_resolution_manifest_rejects_artifact_set_change(tmp_path: Path) -> None:
    packet = tmp_path / "artifact-set"
    shutil.copytree(PACKET_ROOT, packet)
    (packet / "unexpected.json").write_text("{}")
    with pytest.raises(AssertionError, match="^resolution.manifest.artifact_set.exact$"):
        validate_resolution_manifest(packet)
