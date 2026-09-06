from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nsqd.domain.diverge import require_operator
from nsqd.domain.operator_d import (
    operator_d_mapping_proposal_digest,
    validate_operator_d_mapping_contract,
    validate_operator_d_mapping_proposal,
)

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
CONTRACT_PATH = PACKET_ROOT / "analogical-transport-contract.yaml"


def _contract() -> dict[str, object]:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _graph(*, prefix: str, predicate: str) -> dict[str, object]:
    return {
        "nodes": [
            {"id": f"{prefix}-problem", "role": "problem"},
            {"id": f"{prefix}-method", "role": "method"},
        ],
        "relations": [
            {
                "source": f"{prefix}-problem",
                "predicate": predicate,
                "target": f"{prefix}-method",
            }
        ],
    }


def _proposal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "proposal_id": "D-MAP-001",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "source_domain_policy_id": "optimization/1",
        "target_domain_policy_id": "finance/1",
        "source_record_id": "N11-OPT-02",
        "target_record_id": "N11-FIN-04",
        "source_graph": _graph(prefix="opt", predicate="solved_by"),
        "target_graph": _graph(prefix="fin", predicate="explained_by"),
        "allowed_relation_mappings": [
            {"source_predicate": "solved_by", "target_predicate": "explained_by"}
        ],
        "forbidden_surface_attributes": ["title", "venue"],
        "target_constraints": ["no_policy_leak", "no_approved_fact"],
        "mapping_method": "typed_structure_mapping",
        "baselines": ["typed_structure_mapping"],
        "negative_controls": ["surface_similarity_negative_control"],
        "metrics": [
            "held_out_analogy_recovery",
            "role_consistency",
            "target_contradiction_rate",
            "domain_policy_violation_count",
        ],
        "upstream_c": {
            "evidence_sufficient": False,
            "human_accepted": False,
            "selected_bridge_id": None,
        },
        "candidate_inferences": [],
        "provenance": {
            "generated_by": "agent:d-proposer",
            "source_artifact_digests": ["c" * 64],
        },
        "review": {
            "status": "pending",
            "human_reviewer": None,
            "human_approved_at_utc": None,
            "approved_proposal_digest": None,
        },
    }


def test_committed_operator_d_mapping_contract_is_fail_closed() -> None:
    validated = validate_operator_d_mapping_contract(_contract())
    assert validated["record_type"] == "operator_d_mapping_proposal"
    assert validated["template_only"] is True
    assert validated["runtime_authorized"] is False
    assert validated["upstream_c_bridge_sufficient"] is False
    packet = yaml.safe_load((PACKET_ROOT / "operator-d.yaml").read_text(encoding="utf-8"))
    assert packet["analogical_transport_contract"] == "analogical-transport-contract.yaml"
    assert packet["typed_source_graph"] is None
    assert packet["typed_target_graph"] is None
    assert packet["candidate_outputs"] == []
    assert packet["runtime_authorized"] is False
    with pytest.raises(ValueError, match="operator D is not supported"):
        require_operator("D", enabled_operators=frozenset({"A", "B", "E"}))


def test_operator_d_mapping_proposal_is_digest_bound_and_non_authorizing() -> None:
    validated = validate_operator_d_mapping_proposal(_proposal(), contract=_contract())
    assert validated["runtime_authorized"] is False
    assert validated["candidate_inferences"] == []
    assert validated["upstream_c"]["evidence_sufficient"] is False
    assert len(operator_d_mapping_proposal_digest(validated)) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("runtime_authorized", True, "runtime_authorized"),
        ("mapping_method", "surface_similarity_negative_control", "surface similarity"),
        ("candidate_inferences", [{"claim": "transported fact"}], "candidate_inferences"),
        ("source_graph", [], "source_graph"),
        ("target_graph", [], "target_graph"),
        ("baselines", [], "baselines"),
        ("negative_controls", [], "negative_controls"),
        ("metrics", [], "metrics"),
    ],
)
def test_operator_d_mapping_proposal_rejects_unsafe_or_incomplete_rows(
    field: str,
    value: object,
    message: str,
) -> None:
    proposal = _proposal()
    proposal[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())


def test_operator_d_mapping_proposal_rejects_same_policy_and_c_authorization() -> None:
    same_policy = _proposal()
    same_policy["target_domain_policy_id"] = "optimization/1"
    with pytest.raises(ValueError, match="distinct source and target"):
        validate_operator_d_mapping_proposal(same_policy, contract=_contract())

    authorized_c = _proposal()
    authorized_c["upstream_c"] = {
        "evidence_sufficient": True,
        "human_accepted": True,
        "selected_bridge_id": "C-BRIDGE-1",
    }
    with pytest.raises(ValueError, match="upstream C"):
        validate_operator_d_mapping_proposal(authorized_c, contract=_contract())

    leak = _proposal()
    leak["allowed_relation_mappings"] = [
        {"source_predicate": "solved_by", "target_predicate": "title"}
    ]
    with pytest.raises(ValueError, match="forbidden surface"):
        validate_operator_d_mapping_proposal(leak, contract=_contract())

    self_approved = _proposal()
    digest = operator_d_mapping_proposal_digest(self_approved)
    self_approved["review"] = {
        "status": "human_approved",
        "human_reviewer": "agent:d-proposer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approved_proposal_digest": digest,
    }
    with pytest.raises(ValueError, match="independent human reviewer"):
        validate_operator_d_mapping_proposal(self_approved, contract=_contract())

    approved = _proposal()
    approved["review"] = {
        "status": "human_approved",
        "human_reviewer": "human:reviewer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approved_proposal_digest": None,
    }
    review = approved["review"]
    assert isinstance(review, dict)
    review["approved_proposal_digest"] = operator_d_mapping_proposal_digest(approved)
    validated = validate_operator_d_mapping_proposal(approved, contract=_contract())
    assert validated["review"]["human_reviewer"] == "human:reviewer"


@pytest.mark.parametrize(
    ("forbidden_surface_attributes", "surface_attribute"),
    [
        (["venue"], "title"),
        (["title", "topic"], "venue"),
    ],
)
def test_operator_d_mapping_proposal_rejects_forbidden_surface_attribute_widening(
    forbidden_surface_attributes: list[str],
    surface_attribute: str,
) -> None:
    proposal = _proposal()
    proposal["forbidden_surface_attributes"] = forbidden_surface_attributes
    proposal["target_graph"] = _graph(prefix="fin", predicate=surface_attribute)
    proposal["allowed_relation_mappings"] = [
        {"source_predicate": "solved_by", "target_predicate": surface_attribute}
    ]

    with pytest.raises(ValueError, match="forbidden_surface_attributes.*contract"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())


def test_operator_d_mapping_contract_and_proposal_reject_schema_drift() -> None:
    contract = _contract()
    for field, value, message in (
        ("schema_version", 2, "schema_version"),
        ("record_type", "operator_c_bridge", "record_type"),
        ("template_only", False, "template_only"),
        ("requires_upstream_c_bridge", False, "requires_upstream_c_bridge"),
        ("zero_policy_violation_required", False, "zero_policy_violation_required"),
        ("approval_digest_field", "other", "approval_digest_field"),
        ("forbidden_surface_attributes", ["venue"], "forbidden_surface_attributes"),
        ("forbidden_surface_attributes", ["title", "topic"], "forbidden_surface_attributes"),
    ):
        broken = dict(contract)
        broken[field] = value
        with pytest.raises(ValueError, match=message):
            validate_operator_d_mapping_contract(broken)

    proposal = _proposal()
    proposal["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["authorization_state"] = "authorized"
    with pytest.raises(ValueError, match="report_only"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["mapping_method"] = "untyped_guess"
    with pytest.raises(ValueError, match="mapping_method is invalid"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["baselines"] = ["graph_relational_alignment"]
    with pytest.raises(ValueError, match="baselines must include"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["allowed_relation_mappings"] = [
        {"source_predicate": "unknown", "target_predicate": "explained_by"}
    ]
    with pytest.raises(ValueError, match="source_predicate is unbound"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["allowed_relation_mappings"] = [
        {"source_predicate": "solved_by", "target_predicate": "unknown"}
    ]
    with pytest.raises(ValueError, match="target_predicate is unbound"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    raw_graph = proposal["source_graph"]
    assert isinstance(raw_graph, dict)
    source_graph = dict(raw_graph)
    source_graph["nodes"] = [
        {"id": "dup", "role": "problem"},
        {"id": "dup", "role": "method"},
    ]
    source_graph["relations"] = [{"source": "dup", "predicate": "solved_by", "target": "dup"}]
    proposal["source_graph"] = source_graph
    with pytest.raises(ValueError, match="unique ids"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["review"] = {
        "status": "pending",
        "human_reviewer": "human:reviewer",
        "human_approved_at_utc": None,
        "approved_proposal_digest": None,
    }
    with pytest.raises(ValueError, match="unapproved review"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["review"] = {
        "status": "maybe",
        "human_reviewer": None,
        "human_approved_at_utc": None,
        "approved_proposal_digest": None,
    }
    with pytest.raises(ValueError, match="review status"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    with pytest.raises(ValueError, match="string-keyed mapping"):
        validate_operator_d_mapping_contract("missing")
    proposal = _proposal()
    proposal["source_graph"] = "missing"
    with pytest.raises(ValueError, match="source_graph"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["proposal_id"] = "  "
    with pytest.raises(ValueError, match="proposal_id"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
    proposal = _proposal()
    proposal["provenance"] = {
        "generated_by": "agent:d-proposer",
        "source_artifact_digests": ["not-a-digest"],
    }
    with pytest.raises(ValueError, match="sha256"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
