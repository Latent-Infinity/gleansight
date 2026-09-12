from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.nsqd.operator_f_pilot_support import (
    HISTORICAL_RESULT_DIGEST,
    HISTORICAL_RESULT_SHA256,
    RESULT_PATH,
    historical_operator_f_inputs,
)
from tests.nsqd.operator_readiness_expectations import EXPECTED_F_PROTOCOL

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-f-readiness-2026-09-08"
EXPECTED_SOURCE_PATHS = {
    "docs/reviews/nsqd-operator-activation-2026-08-30/operator-f.yaml",
    "docs/reviews/nsqd-operator-activation-2026-08-30/axis-candidate-contract.yaml",
    "docs/reviews/nsqd-operator-activation-2026-08-30/axis-candidate-proposal-validation-target.yaml",
    "docs/reviews/nsqd-operator-activation-2026-08-30/operator-f-validation-target-pilot.json",
    "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/results.json",
    "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/source-ledger.json",
    "docs/reviews/nsqd-projection-review-2026-08-28/final/manifest.toml",
    *{
        f"docs/reviews/nsqd-projection-review-2026-08-28/final/N11-FIN-0{index}.yaml"
        for index in range(1, 6)
    },
    *{
        "docs/reviews/nsqd-projection-review-2026-08-28/final/excerpts/" + name
        for name in (
            "finance-fin-jepa.md",
            "finance-cet.md",
            "finance-fx-transformer.md",
            "finance-exformer.md",
            "finance-denoised-labels.md",
        )
    },
    "tests/fixtures/approved/nsqd/policies/finance-1.toml",
}


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, Mapping)
    assert all(isinstance(key, str) for key in value)
    return {str(key): item for key, item in value.items()}


def _sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return [item for item in value]


def _json(path: Path) -> dict[str, object]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")))


def _validate_packet(packet_root: Path) -> dict[str, object]:
    packet = _json(packet_root / "readiness.json")
    assert set(packet) == {
        "approval_scope",
        "authorization_state",
        "blockers",
        "created_at_utc",
        "decision_thresholds",
        "decision_thresholds_status",
        "evaluation_protocol",
        "evidence_status",
        "evidence_sufficient",
        "inventory",
        "packet_kind",
        "proposal_id",
        "runtime_authorized",
        "schema_admission_authorized",
        "schema_version",
        "source_bindings",
        "source_snapshot_id",
    }
    assert packet["schema_version"] == 1
    assert packet["packet_kind"] == "operator_f_readiness_inventory"
    assert packet["authorization_state"] == "report_only"
    assert packet["runtime_authorized"] is False
    assert packet["schema_admission_authorized"] is False
    assert packet["evidence_sufficient"] is False
    assert packet["proposal_id"] == "F-PROP-001"
    assert packet["approval_scope"] == "evaluation_only"

    bindings = [_mapping(item) for item in _sequence(packet["source_bindings"])]
    assert all(set(binding) == {"path", "role", "sha256"} for binding in bindings)
    assert {binding["path"] for binding in bindings} == EXPECTED_SOURCE_PATHS
    for binding in bindings:
        path = binding["path"]
        digest = binding["sha256"]
        assert isinstance(path, str)
        assert isinstance(digest, str) and len(digest) == 64
        assert hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest() == digest

    inventory = _mapping(packet["inventory"])
    assert set(inventory) == {
        "candidate_observed_record_count",
        "coordinate_eligible_record_count",
        "coordinate_eligible_record_ids",
        "coordinate_ineligible_record_count",
        "coordinate_ineligible_record_ids",
        "independent_source_paper_count",
        "independent_source_papers",
        "total_record_count",
    }
    assert inventory["total_record_count"] == 5
    assert inventory["candidate_observed_record_count"] == 5
    assert inventory["coordinate_eligible_record_count"] == 3
    assert inventory["coordinate_ineligible_record_count"] == 2
    assert inventory["coordinate_eligible_record_ids"] == [
        "N11-FIN-02",
        "N11-FIN-03",
        "N11-FIN-04",
    ]
    assert inventory["coordinate_ineligible_record_ids"] == ["N11-FIN-01", "N11-FIN-05"]
    papers = [_mapping(item) for item in _sequence(inventory["independent_source_papers"])]
    assert inventory["independent_source_paper_count"] == 5
    assert len({paper["source_paper_id"] for paper in papers}) == 5

    evidence = _mapping(packet["evidence_status"])
    assert evidence == {
        "held_out_archive_coverage_gain": None,
        "quality_evidence": "absent",
        "redundancy_evidence": "absent",
        "residual_variation_evidence": "absent",
        "stability_evidence": "absent",
    }
    protocol = _mapping(packet["evaluation_protocol"])
    assert protocol == EXPECTED_F_PROTOCOL
    assert (
        protocol["identical_eligible_record_ids_across_tracks"]
        == inventory["coordinate_eligible_record_ids"]
    )
    assert packet["decision_thresholds_status"] == "human_approval_required"
    assert packet["decision_thresholds"] == {}
    return packet


def test_operator_f_readiness_is_source_bound_and_non_authorizing() -> None:
    _validate_packet(PACKET_ROOT)
    trusted_inputs = historical_operator_f_inputs()
    historical_result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest() == HISTORICAL_RESULT_SHA256
    assert historical_result["result_digest"] == HISTORICAL_RESULT_DIGEST
    assert len(trusted_inputs.records) == 5
    assert sum(record.registered_coordinates is not None for record in trusted_inputs.records) == 3


def test_operator_f_readiness_manifest_replays_deterministically() -> None:
    manifest = _json(PACKET_ROOT / "packet-manifest.json")
    assert set(manifest) == {"artifact_sha256", "packet_digest", "schema_version"}
    artifacts = _mapping(manifest["artifact_sha256"])
    assert set(artifacts) == {"readiness.json"}
    assert (
        artifacts["readiness.json"]
        == hashlib.sha256((PACKET_ROOT / "readiness.json").read_bytes()).hexdigest()
    )
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest()


def test_operator_f_readiness_rejects_missing_source_digest(tmp_path: Path) -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    bindings = _sequence(packet["source_bindings"])
    binding = bindings[0]
    assert isinstance(binding, dict)
    binding.pop("sha256")
    (tmp_path / "readiness.json").write_text(json.dumps(packet), encoding="utf-8")

    with pytest.raises(AssertionError):
        _validate_packet(tmp_path)


@pytest.mark.parametrize("field", sorted(EXPECTED_F_PROTOCOL))
def test_operator_f_readiness_rejects_deleted_protocol_declaration(
    tmp_path: Path,
    field: str,
) -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    protocol = _mapping(packet["evaluation_protocol"])
    protocol.pop(field)
    packet["evaluation_protocol"] = protocol
    (tmp_path / "readiness.json").write_text(json.dumps(packet), encoding="utf-8")

    with pytest.raises(AssertionError):
        _validate_packet(tmp_path)


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("status", "executed"),
        ("split_assignment_algorithm", {}),
        ("split_size_policy", {}),
        ("missingness_exclusion", {}),
        ("metrics", ["density_cost"]),
        ("resampling", {}),
        ("comparison_declarations", {}),
        ("leakage_controls", []),
    ],
)
def test_operator_f_readiness_rejects_tampered_protocol_declaration(
    tmp_path: Path,
    field: str,
    tampered_value: object,
) -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    protocol = _mapping(packet["evaluation_protocol"])
    protocol[field] = tampered_value
    packet["evaluation_protocol"] = protocol
    (tmp_path / "readiness.json").write_text(json.dumps(packet), encoding="utf-8")

    with pytest.raises(AssertionError):
        _validate_packet(tmp_path)
