from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from nsqd.domain.novelty import NOVELTY_K, NOVELTY_THRESHOLD_TAU
from nsqd.domain.project import (
    PROJECTOR_VERSION,
    canonical_reviewed_projection_digest,
)
from nsqd.domain.snapshot import sha256_hex
from nsqd.domain.tau_measurement import (
    build_tau_measurement_export_row,
    export_tau_measurements_jsonl,
    tau_measurement_artifact_digest,
    tau_measurement_export_digest,
)
from nsqd.domain.tau_review import qualify_tau_measurement_pair

AS_OF = datetime(2026, 8, 28, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _reviewed_projection(*, policy_id: str, rank: int) -> dict[str, object]:
    paraphrase = f"neighbor {rank}"
    return {
        "domain_policy_id": policy_id,
        "paraphrase": paraphrase,
        "paraphrase_source": "model_assisted",
        "source_paper_id": f"paper-{policy_id}-{rank}",
        "source": f"doi:10.1/{policy_id}-{rank}",
        "source_abstract_sha256": sha256_hex(f"abstract {rank}".encode()),
        "source_markdown_sha256": sha256_hex(f"markdown {rank}".encode()),
        "paraphrase_sha256": sha256_hex(paraphrase.encode("utf-8")),
        "human_reviewer": "human-reviewer",
        "human_approved_at": AS_OF.isoformat(),
        "review_status": "approved",
    }


def _neighbors(*, policy_id: str = "finance/1") -> list[dict[str, object]]:
    distances = (0.10, 0.20, 0.30, 0.40, 0.50)
    rows: list[dict[str, object]] = []
    for rank, distance in enumerate(distances, start=1):
        record_id = f"rec-{rank}"
        projection = _reviewed_projection(policy_id=policy_id, rank=rank)
        rows.append(
            {
                "record_id": record_id,
                "source_id": projection["source"],
                "source_paper_id": projection["source_paper_id"],
                "domain_policy_id": policy_id,
                "text_digest": projection["paraphrase_sha256"],
                "projector_version": PROJECTOR_VERSION,
                "reviewed_projection_digest": canonical_reviewed_projection_digest(projection),
                "reviewed_projection": projection,
                "distance": distance,
                "rank": rank,
            }
        )
    return rows


def _row(
    *,
    candidate_hash: str = HASH_A,
    policy_id: str = "finance/1",
    snapshot_state: str = "calibration",
    neighbors: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    resolved = neighbors if neighbors is not None else _neighbors(policy_id=policy_id)
    distances: list[float] = []
    for item in resolved:
        distance = item["distance"]
        assert not isinstance(distance, bool)
        assert isinstance(distance, (int, float))
        distances.append(float(distance))
    mean = sum(distances) / len(distances)
    closest = resolved[0]
    pair_id = f"{policy_id}:{candidate_hash}"
    row: dict[str, object] = {
        "pair_id": pair_id,
        "candidate_artifact_hash": candidate_hash,
        "domain_policy_id": policy_id,
        "snapshot_id": HASH_C,
        "snapshot_digest": HASH_C,
        "snapshot_state": snapshot_state,
        "corpus_version": 1,
        "candidate": {
            "artifact_hash": candidate_hash,
            "paraphrase": "candidate text",
            "text_digest": sha256_hex(b"candidate text"),
        },
        "neighbor": dict(closest),
        "neighbors": resolved,
        "measurement": {
            "evidence_mean_distance": mean,
            "k": NOVELTY_K,
            "distances": distances,
            "embedding_model_id": "qwen3-embedding:latest",
            "embedding_model_version": "latest",
            "embedding_dimension": 4096,
            "normalization_policy": "l2",
            "distance_metric": "cosine_distance",
            "algorithm_contract_version": "1.1",
            "measured_at": AS_OF.isoformat(),
        },
    }
    _seal(row)
    return row


def _seal(row: dict[str, object]) -> str:
    digest = tau_measurement_artifact_digest(row)
    row["measurement_artifact_digest"] = digest
    return digest


def _trusted_measurement_digests(rows: list[dict[str, object]]) -> frozenset[str]:
    return frozenset(_seal(row) for row in rows)


def _approved_digests(rows: list[dict[str, object]]) -> frozenset[str]:
    digests: set[str] = set()
    for row in rows:
        neighbors = row["neighbors"]
        assert isinstance(neighbors, list)
        for neighbor in neighbors:
            assert isinstance(neighbor, dict)
            digests.add(str(neighbor["reviewed_projection_digest"]))
    return frozenset(digests)


def _build(row: dict[str, object]) -> dict[str, Any]:
    return build_tau_measurement_export_row(
        row,
        approved_projection_digests=_approved_digests([row]),
        trusted_measurement_digests=_trusted_measurement_digests([row]),
    )


def _export(rows: list[dict[str, object]]) -> bytes:
    return export_tau_measurements_jsonl(
        rows,
        approved_projection_digests=_approved_digests(rows),
        trusted_measurement_digests=_trusted_measurement_digests(rows),
    )


def _digest(rows: list[dict[str, object]]) -> str:
    return tau_measurement_export_digest(
        rows,
        approved_projection_digests=_approved_digests(rows),
        trusted_measurement_digests=_trusted_measurement_digests(rows),
    )


def _measurement(row: dict[str, object]) -> dict[str, object]:
    value = row["measurement"]
    assert isinstance(value, Mapping)
    result: dict[str, object] = {}
    for key, item in value.items():
        assert isinstance(key, str)
        result[key] = item
    return result


def test_export_row_is_one_candidate_with_recomputed_mean() -> None:
    row = _row()
    approved = _approved_digests([row])
    qualified = qualify_tau_measurement_pair(
        row,
        approved_projection_digests=approved,
        trusted_measurement_digests=_trusted_measurement_digests([row]),
    )
    exported = _build(row)
    assert exported["candidate_artifact_hash"] == HASH_A
    assert len(exported["neighbors"]) == NOVELTY_K
    distances = [float(item["distance"]) for item in exported["neighbors"]]
    assert exported["measurement"]["evidence_mean_distance"] == sum(distances) / NOVELTY_K
    assert (
        exported["measurement"]["evidence_mean_distance"]
        == qualified["measurement"]["evidence_mean_distance"]
    )
    assert exported["neighbor"]["record_id"] == exported["neighbors"][0]["record_id"]


def test_export_rejects_duplicate_candidate_or_incomplete_neighbors() -> None:
    duplicate = [_row(), _row()]
    with pytest.raises(ValueError, match="duplicate candidate"):
        _export(duplicate)

    short = _row(neighbors=_neighbors()[:4])
    with pytest.raises(ValueError, match="exactly 5 unique"):
        _build(short)

    mismatched = _row()
    measurement = _measurement(mismatched)
    measurement["evidence_mean_distance"] = 0.99
    mismatched["measurement"] = measurement
    with pytest.raises(ValueError, match="mean"):
        _build(mismatched)


def test_export_rejects_cross_policy_smoke_and_synthetic_rows() -> None:
    cross = _neighbors()
    cross[-1]["domain_policy_id"] = "optimization/1"
    with pytest.raises(ValueError, match="same policy"):
        _build(_row(neighbors=cross))
    with pytest.raises(ValueError, match="calibration or production_valid"):
        _build(_row(snapshot_state="smoke_only"))
    synthetic = _row()
    synthetic["synthetic"] = True
    with pytest.raises(ValueError, match="synthetic"):
        _build(synthetic)


def test_repeated_export_is_byte_and_digest_identical() -> None:
    rows = [_row(candidate_hash=HASH_B), _row(candidate_hash=HASH_A)]
    first = _export(rows)
    second = _export(list(reversed(deepcopy(rows))))
    assert first == second
    assert _digest(rows) == _digest(list(reversed(rows)))
    lines = first.decode("utf-8").strip().split("\n")
    assert len(lines) == 2
    assert HASH_A in lines[0]
    assert HASH_B in lines[1]


def test_export_rejects_hash_mismatch_bad_version_and_duplicate_pair_id() -> None:
    mismatched = _row()
    mismatched["candidate_artifact_hash"] = HASH_B
    with pytest.raises(ValueError, match="candidate artifact hash"):
        _build(mismatched)
    bad_version = _row()
    bad_version["corpus_version"] = 0
    with pytest.raises(ValueError, match="corpus_version"):
        _build(bad_version)
    missing_stamp = _row()
    measurement = _measurement(missing_stamp)
    measurement.pop("measured_at")
    missing_stamp["measurement"] = measurement
    with pytest.raises(ValueError, match="measured_at"):
        _build(missing_stamp)
    first = _row(candidate_hash=HASH_A)
    second = _row(candidate_hash=HASH_B)
    second["pair_id"] = first["pair_id"]
    with pytest.raises(ValueError, match="duplicate pair_id"):
        _export([first, second])


def test_export_rejects_untrusted_projection_and_incomplete_digest_provenance() -> None:
    untrusted = _row()
    with pytest.raises(ValueError, match="approved projection"):
        build_tau_measurement_export_row(
            untrusted,
            approved_projection_digests=frozenset(),
            trusted_measurement_digests=_trusted_measurement_digests([untrusted]),
        )

    missing_candidate_digest = _row()
    candidate = missing_candidate_digest["candidate"]
    assert isinstance(candidate, dict)
    candidate.pop("text_digest")
    with pytest.raises(ValueError, match="text_digest"):
        _build(missing_candidate_digest)

    bad_snapshot_digest = _row()
    bad_snapshot_digest["snapshot_digest"] = "snap-1"
    with pytest.raises(ValueError, match="snapshot_digest"):
        _build(bad_snapshot_digest)

    bad_timestamp = _row()
    measurement = _measurement(bad_timestamp)
    measurement["measured_at"] = "2026-08-28T12:00:00-07:00"
    bad_timestamp["measurement"] = measurement
    with pytest.raises(ValueError, match="UTC"):
        _build(bad_timestamp)


def test_export_rejects_self_consistent_but_unpersisted_measurement() -> None:
    forged = _row()
    _seal(forged)
    with pytest.raises(ValueError, match="trusted persisted grounding"):
        build_tau_measurement_export_row(
            forged,
            approved_projection_digests=_approved_digests([forged]),
            trusted_measurement_digests=frozenset(),
        )

    tampered = _row()
    trusted_digest = str(tampered["measurement_artifact_digest"])
    tampered["corpus_version"] = 2
    with pytest.raises(ValueError, match="artifact digest"):
        build_tau_measurement_export_row(
            tampered,
            approved_projection_digests=_approved_digests([tampered]),
            trusted_measurement_digests=frozenset({trusted_digest}),
        )


def test_export_rejects_duplicate_or_unordered_neighbors() -> None:
    duplicated = _neighbors()
    duplicated[-1] = dict(duplicated[0])
    duplicated[-1]["rank"] = 5
    with pytest.raises(ValueError, match="exactly 5 unique"):
        _build(_row(neighbors=duplicated))
    unordered = list(reversed(_neighbors()))
    for rank, item in enumerate(unordered, start=1):
        item["rank"] = rank
    with pytest.raises(ValueError, match="closest first"):
        _build(_row(neighbors=unordered))
    negative = _neighbors()
    negative[0]["distance"] = -0.1
    with pytest.raises(ValueError, match="finite number"):
        _build(_row(neighbors=negative))
    non_finite = _neighbors()
    non_finite[0]["distance"] = float("inf")
    non_finite_row = _row(neighbors=non_finite)
    non_finite_measurement = _measurement(non_finite_row)
    non_finite_measurement["evidence_mean_distance"] = 0.3
    non_finite_row["measurement"] = non_finite_measurement
    with pytest.raises(ValueError, match="finite number"):
        _build(non_finite_row)


def test_measurement_export_does_not_mutate_runtime_tau() -> None:
    _export([_row()])
    assert NOVELTY_THRESHOLD_TAU == 0.45


def test_grounding_persists_ordered_k_neighbors_for_export() -> None:
    from nsqd.app.use_cases import (
        DivergeUseCase,
        GroundUseCase,
        TauMeasurementEvidenceUseCase,
    )
    from nsqd.domain.snapshot import record_content_hash, snapshot_id
    from nsqd.null_adapters import (
        FixedClock,
        HashParaphraseEmbedder,
        NullCorpusIndex,
        NullCorpusRecordStore,
        NullCorpusSnapshotStore,
        NullFrontierCardStore,
        NullNsqdCandidateStore,
    )

    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    index = NullCorpusIndex()
    embedder = HashParaphraseEmbedder()
    approved_records: list[dict[str, object]] = []
    for rank in range(1, 6):
        projection = _reviewed_projection(policy_id="finance/1", rank=rank)
        if rank == 1:
            projection.pop("source")
        paraphrase = str(projection["paraphrase"])
        source = str(projection.get("source") or f"paper:{projection['source_paper_id']}")
        record = {
            **projection,
            "source": source,
            "record_id": f"rec-{rank}",
            "content_hash": record_content_hash(
                type="paper",
                paraphrase=paraphrase,
                source=source,
            ),
            "type": "paper",
            "harvested_at": AS_OF.isoformat(),
            "projector_version": PROJECTOR_VERSION,
            "reviewed_projection_digest": canonical_reviewed_projection_digest(projection),
            "reviewed_projection": projection,
        }
        if rank == 1:
            record.pop("reviewed_projection")
        records.put(record)
        approved_records.append(record)
    sid = snapshot_id(
        records=[
            {"record_id": str(row["record_id"]), "content_hash": str(row["content_hash"])}
            for row in approved_records
        ],
        schema_version=1,
    )
    snapshots.commit(
        sid,
        [str(row["record_id"]) for row in approved_records],
        schema_version=1,
    )
    for row in approved_records:
        index.upsert(sid, str(row["record_id"]), embedder.embed(str(row["paraphrase"])))
    candidates = NullNsqdCandidateStore()
    digest = DivergeUseCase(
        candidates=candidates,
        cards=NullFrontierCardStore(),
        clock=FixedClock(AS_OF),
    ).run(
        candidate={
            "title": "tau candidate",
            "domain_policy_id": "finance/1",
            "paraphrase": "Approved finance\r\nparaphrase 1",
            "research_descriptor": {
                "mechanism": "flow-driven",
                "target": "drawdown",
                "horizon": "intraday",
            },
        },
        axiom="occupy a missing cell",
        generator_run_id="gen-tau",
    )
    grounding = GroundUseCase(
        snapshots=snapshots,
        records=records,
        index=index,
        candidates=candidates,
        embedder=embedder,
        clock=FixedClock(AS_OF),
    ).run(
        candidate_artifact_hash=digest,
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="calibration",
    )
    neighbors = grounding["neighbors"]
    assert isinstance(neighbors, list)
    assert len(neighbors) == NOVELTY_K
    assert [item["rank"] for item in neighbors] == [1, 2, 3, 4, 5]
    assert len({item["record_id"] for item in neighbors}) == NOVELTY_K
    legacy_neighbor = next(
        item for item in neighbors if str(item["source_id"]).startswith("paper:")
    )
    assert "source" not in legacy_neighbor["reviewed_projection"]
    assert sum(str(item["source_id"]).startswith("doi:10.1/finance/1-") for item in neighbors) == 4
    assert all(item["domain_policy_id"] == "finance/1" for item in neighbors)
    assert all(len(item["text_digest"]) == 64 for item in neighbors)
    approved_digests = _approved_digests([grounding])
    assert all(item["reviewed_projection_digest"] in approved_digests for item in neighbors)
    assert grounding["measurement"]["measured_at"] == AS_OF.isoformat()
    assert grounding["snapshot_digest"] == sid
    assert grounding["candidate"]["paraphrase"] == "Approved finance\nparaphrase 1"
    assert all("reviewed_projection" in item for item in neighbors)
    _build(grounding)
    stored = candidates.get_artifact(digest)
    assert stored is not None
    assert stored["grounding"]["neighbors"] == neighbors
    evidence = TauMeasurementEvidenceUseCase(
        candidates=candidates,
        approved_projection_digests=_approved_digests([grounding]),
    )
    exported = evidence.export_jsonl([digest])
    assert grounding["measurement_artifact_digest"] in exported.decode("utf-8")
    inventory = evidence.inventory([digest])
    assert inventory["qualified_pair_count"] == 1
    assert inventory["ready_for_label_proposals"] is False


def test_application_boundary_rejects_fabricated_inventory_not_in_candidate_store() -> None:
    from nsqd.app.use_cases import TauMeasurementEvidenceUseCase
    from nsqd.null_adapters import NullNsqdCandidateStore

    fabricated_hashes = [sha256_hex(f"fabricated-{index}".encode()) for index in range(120)]
    evidence = TauMeasurementEvidenceUseCase(
        candidates=NullNsqdCandidateStore(),
        approved_projection_digests=frozenset(),
    )
    with pytest.raises(ValueError, match="unknown candidate artifact hash"):
        evidence.inventory(fabricated_hashes)
