from __future__ import annotations

import pytest
import yaml

from nsqd.domain.contract_validation import StructuredInput
from nsqd.domain.diverge import require_operator
from nsqd.domain.operator_d import (
    operator_d_mapping_proposal_digest,
    validate_operator_d_mapping_contract,
    validate_operator_d_mapping_proposal,
)
from tests.nsqd import operator_dg_contract_support

PACKET_ROOT = operator_dg_contract_support.D_PACKET_ROOT
_contract = operator_dg_contract_support.operator_d_contract
_graph = operator_dg_contract_support.operator_d_graph
_proposal = operator_dg_contract_support.operator_d_proposal
_CANONICAL_D_REQUIREMENTS = {
    "required_baselines": ["typed_structure_mapping"],
    "required_negative_controls": ["surface_similarity_negative_control"],
    "required_metrics": [
        "held_out_analogy_recovery",
        "role_consistency",
        "target_contradiction_rate",
        "domain_policy_violation_count",
    ],
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
    upstream = validated["upstream_c"]
    assert isinstance(upstream, dict)
    assert upstream["evidence_sufficient"] is False
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
    value: StructuredInput,
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

    for field, value in (
        ("evidence_sufficient", True),
        ("human_accepted", True),
        ("selected_bridge_id", "C-BRIDGE-1"),
    ):
        authorized_c = _proposal()
        authorized_c["upstream_c"] = {
            "evidence_sufficient": False,
            "human_accepted": False,
            "selected_bridge_id": None,
        } | {field: value}
        with pytest.raises(ValueError, match="upstream C"):
            validate_operator_d_mapping_proposal(authorized_c, contract=_contract())

    leak = _proposal()
    leak["allowed_relation_mappings"] = [
        {"source_predicate": "solved_by", "target_predicate": "title"}
    ]
    with pytest.raises(ValueError, match="forbidden surface"):
        validate_operator_d_mapping_proposal(leak, contract=_contract())


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "allowed_mapping_methods",
            ["typed_structure_mapping", "graph_relational_alignment", "caller_asserted_mapping"],
        ),
        ("forbidden_mapping_methods", ["caller_selected_negative_control"]),
    ],
)
def test_operator_d_mapping_contract_rejects_caller_mutated_mapping_policy(
    field: str,
    value: list[str],
) -> None:
    contract = _contract()
    contract[field] = value

    with pytest.raises(ValueError, match=field):
        validate_operator_d_mapping_contract(contract)


@pytest.mark.parametrize("field", sorted(_CANONICAL_D_REQUIREMENTS))
@pytest.mark.parametrize("mutation", ["deletion", "replacement", "widening", "duplication"])
def test_operator_d_rejects_caller_mutated_canonical_evidence_requirements(
    field: str,
    mutation: str,
) -> None:
    canonical = _CANONICAL_D_REQUIREMENTS[field]
    mutated = {
        "deletion": canonical[1:],
        "replacement": ["attacker_metric"],
        "widening": [*canonical, "attacker_metric"],
        "duplication": [*canonical, canonical[0]],
    }[mutation]
    contract = _contract()
    contract[field] = mutated
    proposal = _proposal()
    proposal[field.removeprefix("required_")] = mutated

    with pytest.raises(ValueError, match=field):
        validate_operator_d_mapping_proposal(proposal, contract=contract)


def test_operator_d_proposal_preserves_required_subset_semantics_for_extras() -> None:
    proposal = _proposal()
    proposal["baselines"] = ["typed_structure_mapping", "descriptive_baseline"]
    proposal["negative_controls"] = [
        "surface_similarity_negative_control",
        "descriptive_negative_control",
    ]
    proposal["metrics"] = [
        *_CANONICAL_D_REQUIREMENTS["required_metrics"],
        "descriptive_metric",
    ]

    validated = validate_operator_d_mapping_proposal(proposal, contract=_contract())

    baselines = validated["baselines"]
    assert isinstance(baselines, list)
    assert baselines[-1] == "descriptive_baseline"


@pytest.mark.parametrize("schema_version", [True, 1.0, "1"])
def test_operator_d_contract_and_proposal_require_integer_schema_version(
    schema_version: StructuredInput,
) -> None:
    contract = _contract()
    contract["schema_version"] = schema_version
    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_d_mapping_contract(contract)

    proposal = _proposal()
    proposal["schema_version"] = schema_version
    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baselines", ("typed_structure_mapping",)),
        (
            "allowed_relation_mappings",
            ({"source_predicate": "solved_by", "target_predicate": "explained_by"},),
        ),
        ("candidate_inferences", ()),
    ],
)
def test_operator_d_proposal_rejects_non_list_json_representations(
    field: str,
    value: StructuredInput,
) -> None:
    proposal = _proposal()
    proposal[field] = value

    with pytest.raises(ValueError, match=field):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())


def test_operator_d_mapping_proposal_rejects_removed_policy_leakage_guard() -> None:
    proposal = _proposal()
    proposal["target_constraints"] = ["no_approved_fact"]

    with pytest.raises(ValueError, match="target_constraints"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())


def test_operator_d_mapping_proposal_rejects_dangling_typed_graph_relation() -> None:
    proposal = _proposal()
    source_graph = _graph(prefix="opt", predicate="solved_by")
    source_graph["relations"] = [
        {"source": "opt-problem", "predicate": "solved_by", "target": "missing-node"}
    ]
    proposal["source_graph"] = source_graph

    with pytest.raises(ValueError, match="relations must reference graph nodes"):
        validate_operator_d_mapping_proposal(proposal, contract=_contract())
