"""Public operation lifecycle, provenance failures, and report destination checks."""

from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter

from tests.api.nsqd.test_workflows import FIXTURES, ScratchRuntime, invoke, mapping


def test_diverge_ground_gate_rescore_and_current_metadata(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    smoke = mapping(
        invoke(
            runtime,
            "nsqd.skeleton.run",
            {
                "candidate_fixture": str(FIXTURES / "gamma-flow.yaml"),
                "axiom": "stationarity",
            },
        )
    )
    snapshot = smoke["snapshot_id"]
    diverged = mapping(
        invoke(
            runtime,
            "nsqd.candidates.diverge",
            {
                "candidate_fixture": str(FIXTURES / "mechanism-free.yaml"),
                "axiom": "stationarity",
                "snapshot_id": snapshot,
                "domain_policy_id": "finance/1",
                "snapshot_state": "smoke_only",
            },
        )
    )
    artifact = diverged["candidate_artifact_hash"]
    snapshot_row = mapping(invoke(runtime, "nsqd.snapshots.get", {"id": snapshot}))
    version = snapshot_row["schema_version"]
    grounded = mapping(
        invoke(
            runtime,
            "nsqd.candidates.ground",
            {
                "candidate_artifact_hash": artifact,
                "snapshot_id": snapshot,
                "corpus_version": version,
                "snapshot_state": "smoke_only",
            },
        )
    )
    assert grounded["grounding_class"] == "unevaluated"
    gated = mapping(
        invoke(
            runtime,
            "nsqd.cards.gate",
            {
                "candidate_artifact_hash": artifact,
                "snapshot_id": snapshot,
                "corpus_version": version,
                "snapshot_state": "smoke_only",
                "evaluator_run_id": "api-test",
            },
        )
    )
    assert gated["card_decision"] == "rejected"
    rescored = mapping(
        invoke(
            runtime,
            "nsqd.cards.rescore",
            {
                "card_id": artifact,
                "current_snapshot_id": snapshot,
                "current_corpus_version": version,
                "snapshot_state": "smoke_only",
            },
        )
    )
    assert mapping(rescored["card"])["card_decision"] == "rejected"
    with pytest.raises(ValueError):
        invoke(
            runtime,
            "nsqd.candidates.ground",
            {
                "candidate_artifact_hash": artifact,
                "snapshot_id": "missing-source",
                "corpus_version": version,
                "snapshot_state": "calibration",
            },
        )
    with pytest.raises(ValueError):
        invoke(
            runtime,
            "nsqd.cards.rescore",
            {
                "card_id": artifact,
                "current_snapshot_id": "missing-current",
                "current_corpus_version": version,
                "snapshot_state": "calibration",
            },
        )
    jobs = mapping(invoke(runtime, "nsqd.jobs.list", {}))
    rows = TypeAdapter(list[dict[str, JsonValue]]).validate_python(jobs["items"])
    assert sum(row["status"] == "failed" for row in rows) == 2


def test_acquisition_rejects_tampered_projection_before_composition(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("schema_version = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        invoke(
            runtime,
            "nsqd.corpus.acquire",
            {
                "snapshot_id": "empty",
                "domain_policy_id": "finance/1",
                "approved_projections": [str(FIXTURES / "paper-a.yaml")],
                "approval_manifest": str(manifest),
            },
        )
    assert mapping(invoke(runtime, "nsqd.digests.list", {}))["digests"] == []
    assert not (tmp_path / "data/papers.sqlite").exists()


def test_tau_rejects_tampered_packet_without_writing_reports(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    packet = tmp_path / "packet.json"
    packet.write_text('{"rows":[{}],"packet_digest":"tampered"}', encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        invoke(
            runtime,
            "nsqd.tau.evaluate",
            {
                "candidate_artifact_hashes": ["a" * 64],
                "inputs": [str(packet)],
            },
        )
    assert not (tmp_path / "output").exists()
