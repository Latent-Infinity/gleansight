from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from nsqd.domain.diverge import require_operator
from nsqd.domain.operator_f import (
    operator_f_axis_proposal_digest,
    validate_operator_f_axis_proposal,
)

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
PROPOSAL_PATH = PACKET_ROOT / "axis-candidate-proposal-validation-target.yaml"
JEPA_RESULTS_PATH = PACKET_ROOT.parent / "nsqd-jepa-ideas-gaps-2026-09-01" / "results.json"
APPROVED_SNAPSHOT_ID = "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
JEPA_RESULTS_SHA256 = "cdcb6eb1c274c17cbb71c5a76cf8c439d0bc021b2149225b4b27b550360705f2"


def _load_contract() -> dict[str, object]:
    loaded = yaml.safe_load(
        (PACKET_ROOT / "axis-candidate-contract.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def test_committed_validation_target_proposal_is_evaluation_only_and_non_admitting() -> None:
    loaded = yaml.safe_load(PROPOSAL_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    with pytest.raises(ValueError, match="trusted approval"):
        validate_operator_f_axis_proposal(loaded, contract=_load_contract())
    hypothesis = json.loads(JEPA_RESULTS_PATH.read_text(encoding="utf-8"))[
        "candidate_axis_hypothesis"
    ]
    packet = yaml.safe_load((PACKET_ROOT / "operator-f.yaml").read_text(encoding="utf-8"))
    assert loaded["proposal_id"] == "F-PROP-001"
    assert loaded["authorization_state"] == "report_only"
    assert loaded["runtime_authorized"] is False
    assert loaded["schema_mutation_authorized"] is False
    assert loaded["domain_policy_id"] == "finance/1"
    assert loaded["source_snapshot_ids"] == [APPROVED_SNAPSHOT_ID]
    assert loaded["existing_axis_inventory"] == ["mechanism", "target", "horizon"]
    assert loaded["candidate_axis"]["name"] == hypothesis["axis_id"] == "validation_target"
    assert loaded["candidate_axis"]["semantic_definition"] == hypothesis["definition"]
    assert loaded["candidate_axis"]["measurement_protocol"] == hypothesis["measurement_protocol"]
    assert loaded["review"] == {
        "status": "human_approved",
        "human_reviewer": "human:firestrand",
        "human_approved_at_utc": "2026-09-07T09:36:57Z",
        "approval_scope": "evaluation_only",
        "approved_proposal_digest": (
            "cbbaf10797b2acb0ebf34b4d62fa37b0e3ec5dfad41c7989334519d9a5962bb6"
        ),
    }
    assert hypothesis["schema_admission_recommended"] is False
    assert hypothesis["status"] == "needs_more_corpus"
    assert loaded["provenance"]["source_artifact_digests"] == [JEPA_RESULTS_SHA256]
    assert len(operator_f_axis_proposal_digest(loaded)) == 64
    assert packet["candidate_axes"][0]["source"] == "axis-candidate-proposal-validation-target.yaml"
    assert packet["candidate_axes"][0]["schema_admission_recommended"] is False
    assert packet["ablation_executed"] is True
    assert packet["runtime_authorized"] is False
    with pytest.raises(ValueError, match="operator F is not supported"):
        require_operator("F", enabled_operators=frozenset({"A", "B", "E"}))
