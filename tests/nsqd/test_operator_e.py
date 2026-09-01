from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nsqd.domain.diverge import require_operator
from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU
from nsqd.domain.operator_e import bind_operator_e_inventory

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
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


def _packet(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operator": "E",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": False,
        "approved_component_inventory": {
            "finance/1": ["DATA-NSQD-03", "N11-FIN-01"],
            "optimization/1": ["DATA-NSQD-04", "N11-OPT-01"],
        },
        "candidate_combinations": [],
        "candidate_outputs": [],
        "tracks": {
            "same_policy": {"policy_rule": "one domain_policy_id"},
            "cross_policy": {"policy_rule": "bind source and target"},
        },
    }
    payload.update(overrides)
    return payload


def _record(
    record_id: str,
    *,
    domain_policy_id: str,
    kind: str = "corpus-paper-paraphrase",
    review_status: str = "approved",
) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": kind,
        "review_status": review_status,
        "domain_policy_id": domain_policy_id,
        "title": record_id,
        "source_paper_id": f"id:{record_id}",
    }


APPROVED = {
    "DATA-NSQD-03": _record("DATA-NSQD-03", domain_policy_id="finance/1"),
    "N11-FIN-01": _record("N11-FIN-01", domain_policy_id="finance/1"),
    "DATA-NSQD-04": _record("DATA-NSQD-04", domain_policy_id="optimization/1"),
    "N11-OPT-01": _record("N11-OPT-01", domain_policy_id="optimization/1"),
    "DATA-NSQD-01": _record(
        "DATA-NSQD-01",
        domain_policy_id="finance/1",
        kind="candidate-requirement-card",
    ),
}


def test_bind_operator_e_inventory_keeps_tracks_unpooled() -> None:
    bound = bind_operator_e_inventory(_packet(), approved_records=APPROVED)
    assert bound["candidate_combinations"] == []
    assert bound["co_occurrence_snapshot_id"] is None
    assert bound["evidence_sufficient"] is False
    assert bound["runtime_authorized"] is False
    assert bound["tracks"]["same_policy"]["finance/1"] == ["DATA-NSQD-03", "N11-FIN-01"]
    assert bound["tracks"]["same_policy"]["optimization/1"] == ["DATA-NSQD-04", "N11-OPT-01"]
    assert bound["tracks"]["cross_policy"]["pooled"] is False
    assert bound["tracks"]["cross_policy"]["source_domain_policy_ids"] == [
        "finance/1",
        "optimization/1",
    ]


def test_bind_operator_e_inventory_rejects_requirement_cards_and_policy_mismatch() -> None:
    with pytest.raises(ValueError, match="requirement-card"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": ["DATA-NSQD-01"],
                    "optimization/1": ["DATA-NSQD-04"],
                }
            ),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="does not match"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": ["DATA-NSQD-04"],
                    "optimization/1": ["DATA-NSQD-03"],
                }
            ),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="operator E packet"):
        bind_operator_e_inventory(_packet(operator="C"), approved_records=APPROVED)
    with pytest.raises(ValueError, match="candidate combinations"):
        bind_operator_e_inventory(
            _packet(candidate_combinations=[{"components": ["DATA-NSQD-03", "N11-FIN-01"]}]),
            approved_records=APPROVED,
        )
    for candidate_combinations in (None, "missing"):
        with pytest.raises(ValueError, match="candidate_combinations must be an empty list"):
            bind_operator_e_inventory(
                _packet(candidate_combinations=candidate_combinations),
                approved_records=APPROVED,
            )
    missing_combinations = _packet()
    missing_combinations.pop("candidate_combinations")
    with pytest.raises(ValueError, match="candidate_combinations must be an empty list"):
        bind_operator_e_inventory(missing_combinations, approved_records=APPROVED)
    with pytest.raises(ValueError, match="candidate_outputs must be an empty list"):
        bind_operator_e_inventory(
            _packet(candidate_outputs=[{"candidate_id": "invented"}]),
            approved_records=APPROVED,
        )
    missing_outputs = _packet()
    missing_outputs.pop("candidate_outputs")
    with pytest.raises(ValueError, match="candidate_outputs must be an empty list"):
        bind_operator_e_inventory(missing_outputs, approved_records=APPROVED)
    with pytest.raises(ValueError, match="unknown record"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": ["N11-FIN-99"],
                    "optimization/1": ["DATA-NSQD-04"],
                }
            ),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="report_only"):
        bind_operator_e_inventory(
            _packet(authorization_state="authorized"), approved_records=APPROVED
        )
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_e_inventory(_packet(runtime_authorized=True), approved_records=APPROVED)
    with pytest.raises(ValueError, match="evidence_sufficient must be false"):
        bind_operator_e_inventory(_packet(evidence_sufficient=True), approved_records=APPROVED)
    pending = dict(APPROVED)
    pending["N11-FIN-01"] = _record(
        "N11-FIN-01", domain_policy_id="finance/1", review_status="pending"
    )
    with pytest.raises(ValueError, match="must be approved"):
        bind_operator_e_inventory(_packet(), approved_records=pending)
    other_kind = dict(APPROVED)
    other_kind["N11-FIN-01"] = _record("N11-FIN-01", domain_policy_id="finance/1", kind="essay")
    with pytest.raises(ValueError, match="approved paraphrases"):
        bind_operator_e_inventory(_packet(), approved_records=other_kind)
    with pytest.raises(ValueError, match="unknown domain policies"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": ["DATA-NSQD-03"],
                    "optimization/1": ["DATA-NSQD-04"],
                    "biology/1": ["N11-FIN-01"],
                }
            ),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="approved_component_inventory is required"):
        bind_operator_e_inventory(
            _packet(approved_component_inventory="missing"), approved_records=APPROVED
        )
    with pytest.raises(ValueError, match="keys must be strings"):
        bind_operator_e_inventory(
            _packet(approved_component_inventory={1: ["DATA-NSQD-03"]}),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="finance/1 is required"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": "DATA-NSQD-03",
                    "optimization/1": ["DATA-NSQD-04"],
                }
            ),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="values must be strings"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": ["DATA-NSQD-03", 3],
                    "optimization/1": ["DATA-NSQD-04"],
                }
            ),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="finance/1 is required"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": [],
                    "optimization/1": ["DATA-NSQD-04"],
                }
            ),
            approved_records=APPROVED,
        )
    blank_policy = dict(APPROVED)
    blank_policy["N11-FIN-01"] = dict(APPROVED["N11-FIN-01"], domain_policy_id="  ")
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        bind_operator_e_inventory(_packet(), approved_records=blank_policy)
    with pytest.raises(ValueError, match="duplicate record_id"):
        bind_operator_e_inventory(
            _packet(
                approved_component_inventory={
                    "finance/1": ["DATA-NSQD-03", "DATA-NSQD-03"],
                    "optimization/1": ["DATA-NSQD-04"],
                }
            ),
            approved_records=APPROVED,
        )


def test_executable_tau_and_inventory_do_not_authorize_operator_e() -> None:
    bound = bind_operator_e_inventory(_packet(), approved_records=APPROVED)
    assert NOVELTY_THRESHOLD_TAU == 0.45
    assert bound["runtime_authorized"] is False
    with pytest.raises(ValueError, match="operator E is not supported"):
        require_operator("E", enabled_operators=frozenset({"A", "B"}))


def test_committed_operator_e_packet_binds_approved_inventory_only() -> None:
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
    bound = bind_operator_e_inventory(packet, approved_records=records)
    assert bound["candidate_combinations"] == []
    assert packet["candidate_combinations"] == []
    assert packet["candidate_outputs"] == []
    assert packet["runtime_authorized"] is False
    assert packet["evidence_sufficient"] is False
    assert packet["algorithm_identity"] == "not_run"
    assert "DATA-NSQD-03" in bound["tracks"]["same_policy"]["finance/1"]
    assert "DATA-NSQD-04" in bound["tracks"]["same_policy"]["optimization/1"]
