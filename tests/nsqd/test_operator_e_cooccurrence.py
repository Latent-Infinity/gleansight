from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from nsqd.domain.diverge import require_operator
from nsqd.domain.operator_e import (
    OPERATOR_E_ATYPICALITY_INTERPRETATION,
    bind_operator_e_cooccurrence_snapshot,
    bind_operator_e_inventory,
)
from nsqd.domain.snapshot import canonical_json, sha256_hex

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
JEPA_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
)
PROJECTION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reviews"
    / "nsqd-projection-review-2026-08-28"
    / "final"
)
APPROVED_NSQD_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "approved" / "nsqd"
)


def _record(record_id: str, *, domain_policy_id: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": "corpus-paper-paraphrase",
        "review_status": "approved",
        "domain_policy_id": domain_policy_id,
        "title": record_id,
        "source_paper_id": f"id:{record_id}",
    }


def _inventory() -> dict[str, Any]:
    declared_snapshot = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    return bind_operator_e_inventory(
        {
            "operator": "E",
            "authorization_state": "report_only",
            "runtime_authorized": False,
            "evidence_sufficient": False,
            "candidate_combinations": [],
            "candidate_outputs": [],
            "co_occurrence_snapshots": {
                "same_policy:finance/1": {
                    "source": "results.json",
                    "source_packet_digest": "a" * 64,
                    "review_summary_packet_digest": "b" * 64,
                    "snapshot_id": declared_snapshot["snapshot_id"],
                    "record_ids": declared_snapshot["record_ids"],
                    "atypicality_interpretation": OPERATOR_E_ATYPICALITY_INTERPRETATION,
                }
            },
            "approved_component_inventory": {
                "finance/1": ["DATA-NSQD-03", "N11-FIN-01", "N11-FIN-02"],
                "optimization/1": ["DATA-NSQD-04", "N11-OPT-01"],
            },
        },
        approved_records={
            "DATA-NSQD-03": _record("DATA-NSQD-03", domain_policy_id="finance/1"),
            "N11-FIN-01": _record("N11-FIN-01", domain_policy_id="finance/1"),
            "N11-FIN-02": _record("N11-FIN-02", domain_policy_id="finance/1"),
            "DATA-NSQD-04": _record("DATA-NSQD-04", domain_policy_id="optimization/1"),
            "N11-OPT-01": _record("N11-OPT-01", domain_policy_id="optimization/1"),
        },
    )


def _snapshot(record_ids: list[str], *, track: str = "same_policy:finance/1") -> dict[str, Any]:
    feature_matrix = {record_id: ["feature"] for record_id in record_ids}
    feature_evidence = {f"{record_id}:feature": ["FACT-1"] for record_id in record_ids}
    preimage = {
        "record_ids": record_ids,
        "feature_matrix": feature_matrix,
        "feature_evidence": feature_evidence,
    }
    return {
        "method": "exact co-occurrence of approved claim-feature tags",
        "track": track,
        "source": "results.json",
        "source_packet_digest": "a" * 64,
        "review_summary_packet_digest": "b" * 64,
        "record_ids": record_ids,
        "feature_matrix": feature_matrix,
        "feature_evidence": feature_evidence,
        "snapshot_id": sha256_hex(canonical_json(preimage)),
    }


def test_bind_operator_e_cooccurrence_keeps_finance_track_unpooled() -> None:
    bound = bind_operator_e_cooccurrence_snapshot(
        _inventory(),
        _snapshot(["N11-FIN-01", "N11-FIN-02"]),
    )
    assert bound["co_occurrence_track"] == "same_policy:finance/1"
    assert bound["co_occurrence_record_ids"] == ["N11-FIN-01", "N11-FIN-02"]
    assert bound["candidate_combinations"] == []
    assert bound["candidate_outputs"] == []
    assert bound["atypicality_interpretation"] == OPERATOR_E_ATYPICALITY_INTERPRETATION
    assert bound["operator_a_baseline_status"] == "not_executed"
    assert bound["operator_b_baseline_status"] == "not_executed"
    assert bound["evidence_sufficient"] is False
    assert bound["runtime_authorized"] is False


def test_bind_operator_e_cooccurrence_rejects_interpretation_drift() -> None:
    inventory = _inventory()
    inventory["co_occurrence_snapshots"]["same_policy:finance/1"]["atypicality_interpretation"] = (
        "novelty"
    )
    with pytest.raises(ValueError, match="atypicality_interpretation"):
        bind_operator_e_cooccurrence_snapshot(
            inventory,
            _snapshot(["N11-FIN-01", "N11-FIN-02"]),
        )


def test_bind_operator_e_cooccurrence_rejects_mixed_policy_and_bad_digest() -> None:
    inventory = _inventory()
    with pytest.raises(ValueError, match="exactly one same-policy"):
        bind_operator_e_cooccurrence_snapshot(
            inventory,
            _snapshot(["N11-FIN-01", "N11-OPT-01"], track="same_policy:finance/1"),
        )
    broken = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    broken["snapshot_id"] = "0" * 64
    with pytest.raises(ValueError, match="snapshot_id"):
        bind_operator_e_cooccurrence_snapshot(inventory, broken)
    with pytest.raises(ValueError, match="not in the Operator E inventory"):
        bind_operator_e_cooccurrence_snapshot(
            inventory,
            _snapshot(["N11-FIN-04"]),
        )
    authorized = dict(inventory)
    authorized["runtime_authorized"] = True
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_e_cooccurrence_snapshot(authorized, _snapshot(["N11-FIN-01"]))
    sufficient = dict(inventory)
    sufficient["evidence_sufficient"] = True
    with pytest.raises(ValueError, match="evidence_sufficient must be false"):
        bind_operator_e_cooccurrence_snapshot(sufficient, _snapshot(["N11-FIN-01"]))
    generated = dict(inventory)
    generated["candidate_combinations"] = [{"components": ["N11-FIN-01", "N11-FIN-02"]}]
    with pytest.raises(ValueError, match="candidate combinations"):
        bind_operator_e_cooccurrence_snapshot(generated, _snapshot(["N11-FIN-01"]))
    wrong_track = _snapshot(["N11-FIN-01", "N11-FIN-02"], track="same_policy:optimization/1")
    with pytest.raises(ValueError, match="snapshot track"):
        bind_operator_e_cooccurrence_snapshot(inventory, wrong_track)
    mismatched_matrix = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    mismatched_matrix["feature_matrix"] = {"N11-FIN-01": ["feature"]}
    mismatched_matrix["snapshot_id"] = sha256_hex(
        canonical_json(
            {
                "record_ids": mismatched_matrix["record_ids"],
                "feature_matrix": mismatched_matrix["feature_matrix"],
                "feature_evidence": mismatched_matrix["feature_evidence"],
            }
        )
    )
    with pytest.raises(ValueError, match="feature_matrix keys"):
        bind_operator_e_cooccurrence_snapshot(inventory, mismatched_matrix)


def test_bind_operator_e_cooccurrence_rejects_ambiguous_or_unbound_evidence() -> None:
    inventory = _inventory()
    duplicate_records = _snapshot(["N11-FIN-01", "N11-FIN-01"])
    with pytest.raises(ValueError, match="duplicate record_id"):
        bind_operator_e_cooccurrence_snapshot(inventory, duplicate_records)

    orphan_evidence = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    orphan_evidence["feature_evidence"]["ORPHAN:feature"] = ["FACT-X"]
    orphan_evidence["snapshot_id"] = sha256_hex(
        canonical_json(
            {
                "record_ids": orphan_evidence["record_ids"],
                "feature_matrix": orphan_evidence["feature_matrix"],
                "feature_evidence": orphan_evidence["feature_evidence"],
            }
        )
    )
    inventory["co_occurrence_snapshots"]["same_policy:finance/1"]["snapshot_id"] = orphan_evidence[
        "snapshot_id"
    ]
    with pytest.raises(ValueError, match="feature_evidence keys"):
        bind_operator_e_cooccurrence_snapshot(inventory, orphan_evidence)

    duplicate_feature = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    duplicate_feature["feature_matrix"]["N11-FIN-01"] = ["feature", "feature"]
    with pytest.raises(ValueError, match="duplicate feature"):
        bind_operator_e_cooccurrence_snapshot(_inventory(), duplicate_feature)

    duplicate_evidence = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    duplicate_evidence["feature_evidence"]["N11-FIN-01:feature"] = ["FACT-1", "FACT-1"]
    with pytest.raises(ValueError, match="duplicate evidence id"):
        bind_operator_e_cooccurrence_snapshot(_inventory(), duplicate_evidence)

    recomputed_but_undeclared = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    recomputed_but_undeclared["feature_matrix"]["N11-FIN-01"] = ["other_feature"]
    recomputed_but_undeclared["feature_evidence"] = {
        "N11-FIN-01:other_feature": ["FACT-2"],
        "N11-FIN-02:feature": ["FACT-1"],
    }
    recomputed_but_undeclared["snapshot_id"] = sha256_hex(
        canonical_json(
            {
                "record_ids": recomputed_but_undeclared["record_ids"],
                "feature_matrix": recomputed_but_undeclared["feature_matrix"],
                "feature_evidence": recomputed_but_undeclared["feature_evidence"],
            }
        )
    )
    with pytest.raises(ValueError, match="packet-declared snapshot_id"):
        bind_operator_e_cooccurrence_snapshot(_inventory(), recomputed_but_undeclared)

    mismatched_declared_records = _inventory()
    mismatched_declared_records["co_occurrence_snapshots"]["same_policy:finance/1"][
        "record_ids"
    ] = ["N11-FIN-02", "N11-FIN-01"]
    with pytest.raises(ValueError, match="packet-declared record_ids"):
        bind_operator_e_cooccurrence_snapshot(
            mismatched_declared_records,
            _snapshot(["N11-FIN-01", "N11-FIN-02"]),
        )

    mismatched_source = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    mismatched_source["source"] = "other-results.json"
    with pytest.raises(ValueError, match="packet-declared source"):
        bind_operator_e_cooccurrence_snapshot(_inventory(), mismatched_source)

    mismatched_packet_digest = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    mismatched_packet_digest["source_packet_digest"] = "b" * 64
    with pytest.raises(ValueError, match="packet-declared source_packet_digest"):
        bind_operator_e_cooccurrence_snapshot(_inventory(), mismatched_packet_digest)

    mismatched_review_digest = _snapshot(["N11-FIN-01", "N11-FIN-02"])
    mismatched_review_digest["review_summary_packet_digest"] = "c" * 64
    with pytest.raises(ValueError, match="packet-declared review digest"):
        bind_operator_e_cooccurrence_snapshot(_inventory(), mismatched_review_digest)

    generated_outputs = _inventory()
    generated_outputs["candidate_outputs"] = [{"candidate_id": "invented"}]
    with pytest.raises(ValueError, match="candidate_outputs must be an empty list"):
        bind_operator_e_cooccurrence_snapshot(
            generated_outputs,
            _snapshot(["N11-FIN-01", "N11-FIN-02"]),
        )


def test_jepa_finance_snapshot_binds_without_authorizing_operator_e() -> None:
    packet = yaml.safe_load((PACKET_ROOT / "operator-e.yaml").read_text(encoding="utf-8"))
    records: dict[str, Any] = {}
    for record_id in packet["approved_component_inventory"]["finance/1"]:
        path = (
            APPROVED_NSQD_ROOT / "gamma-fragility.yaml"
            if record_id == "DATA-NSQD-03"
            else PROJECTION_ROOT / f"{record_id}.yaml"
        )
        records[record_id] = yaml.safe_load(path.read_text(encoding="utf-8"))
    for record_id in packet["approved_component_inventory"]["optimization/1"]:
        path = (
            APPROVED_NSQD_ROOT / "paper-a.yaml"
            if record_id == "DATA-NSQD-04"
            else PROJECTION_ROOT / f"{record_id}.yaml"
        )
        records[record_id] = yaml.safe_load(path.read_text(encoding="utf-8"))
    inventory = bind_operator_e_inventory(packet, approved_records=records)
    results = json.loads((JEPA_ROOT / "results.json").read_text(encoding="utf-8"))
    summary = json.loads((JEPA_ROOT / "review-summary.json").read_text(encoding="utf-8"))
    declaration = packet["co_occurrence_snapshots"]["same_policy:finance/1"]
    assert declaration["source"] == "../nsqd-jepa-ideas-gaps-2026-09-01/results.json"
    assert declaration["source_packet_digest"] == summary["artifact_sha256"]["results.json"]
    assert declaration["review_summary_packet_digest"] == summary["packet_digest"]
    snapshot = dict(results["cooccurrence_snapshot"])
    snapshot["source"] = declaration["source"]
    snapshot["source_packet_digest"] = summary["artifact_sha256"]["results.json"]
    snapshot["review_summary_packet_digest"] = summary["packet_digest"]
    bound = bind_operator_e_cooccurrence_snapshot(inventory, snapshot)
    assert bound["co_occurrence_snapshot_id"] == results["cooccurrence_snapshot"]["snapshot_id"]
    assert bound["co_occurrence_track"] == "same_policy:finance/1"
    assert "DATA-NSQD-03" not in bound["co_occurrence_record_ids"]
    assert bound["candidate_combinations"] == []
    assert packet["candidate_combinations"] == []
    assert bound["runtime_authorized"] is False
    with pytest.raises(ValueError, match="not enabled by composition"):
        require_operator("E", enabled_operators=frozenset({"A", "B"}))
