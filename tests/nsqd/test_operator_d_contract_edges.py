from __future__ import annotations

import pytest

from nsqd.domain.operator_d import (
    validate_operator_d_mapping_contract,
    validate_operator_d_mapping_proposal,
)
from tests.nsqd.operator_dg_contract_support import (
    operator_d_contract,
    operator_d_proposal,
)


def test_operator_d_mapping_contract_and_proposal_reject_schema_drift() -> None:
    contract = operator_d_contract()
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

    proposal = operator_d_proposal()
    proposal["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["authorization_state"] = "authorized"
    with pytest.raises(ValueError, match="report_only"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["mapping_method"] = "untyped_guess"
    with pytest.raises(ValueError, match="mapping_method is invalid"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["baselines"] = ["graph_relational_alignment"]
    with pytest.raises(ValueError, match="baselines must include"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["allowed_relation_mappings"] = [
        {"source_predicate": "unknown", "target_predicate": "explained_by"}
    ]
    with pytest.raises(ValueError, match="source_predicate is unbound"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["allowed_relation_mappings"] = [
        {"source_predicate": "solved_by", "target_predicate": "unknown"}
    ]
    with pytest.raises(ValueError, match="target_predicate is unbound"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
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
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["review"] = {
        "status": "pending",
        "human_reviewer": "human:reviewer",
        "human_approved_at_utc": None,
        "approved_proposal_digest": None,
    }
    with pytest.raises(ValueError, match="unapproved review"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["review"] = {
        "status": "maybe",
        "human_reviewer": None,
        "human_approved_at_utc": None,
        "approved_proposal_digest": None,
    }
    with pytest.raises(ValueError, match="review status"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    with pytest.raises(ValueError, match="string-keyed mapping"):
        validate_operator_d_mapping_contract("missing")
    proposal = operator_d_proposal()
    proposal["source_graph"] = "missing"
    with pytest.raises(ValueError, match="source_graph"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["proposal_id"] = "  "
    with pytest.raises(ValueError, match="proposal_id"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
    proposal = operator_d_proposal()
    proposal["provenance"] = {
        "generated_by": "agent:d-proposer",
        "source_artifact_digests": ["not-a-digest"],
    }
    with pytest.raises(ValueError, match="sha256"):
        validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())
