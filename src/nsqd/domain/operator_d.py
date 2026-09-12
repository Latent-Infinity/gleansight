from __future__ import annotations

import copy
from collections.abc import Mapping

from nsqd.domain import contract_validation
from nsqd.domain.contract_validation import StructuredInput, StructuredValue
from nsqd.domain.operator_approval import TrustedOperatorApproval, require_operator_d_approval
from nsqd.domain.snapshot import canonical_json, sha256_hex

_mapping = contract_validation.as_mapping
_mapping_list = contract_validation.mapping_list
_exact_fields = contract_validation.require_exact_fields
_exact_string_set = contract_validation.require_exact_string_set
_required_string = contract_validation.required_string
_schema_version = contract_validation.require_schema_version
_sha256_list = contract_validation.sha256_list
_string_list = contract_validation.string_list
_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "template_only",
        "runtime_authorized",
        "requires_upstream_c_bridge",
        "upstream_c_bridge_sufficient",
        "allowed_mapping_methods",
        "forbidden_mapping_methods",
        "forbidden_surface_attributes",
        "required_baselines",
        "required_negative_controls",
        "required_metrics",
        "zero_policy_violation_required",
        "approval_digest_field",
        "admission_rules",
        "method_references",
    }
)
_FORBIDDEN_SURFACE_ATTRIBUTES = frozenset({"title", "venue"})
_ALLOWED_MAPPING_METHODS = frozenset({"typed_structure_mapping", "graph_relational_alignment"})
_FORBIDDEN_MAPPING_METHODS = frozenset({"surface_similarity_negative_control"})
_REQUIRED_TARGET_CONSTRAINTS = frozenset({"no_policy_leak", "no_approved_fact"})
_REQUIRED_BASELINES = frozenset({"typed_structure_mapping"})
_REQUIRED_NEGATIVE_CONTROLS = frozenset({"surface_similarity_negative_control"})
_REQUIRED_METRICS = frozenset(
    {"held_out_analogy_recovery", "role_consistency", "target_contradiction_rate"}
    | {"domain_policy_violation_count"}
)
_PROPOSAL_FIELDS = frozenset(
    {
        "schema_version",
        "proposal_id",
        "authorization_state",
        "runtime_authorized",
        "source_domain_policy_id",
        "target_domain_policy_id",
        "source_record_id",
        "target_record_id",
        "source_graph",
        "target_graph",
        "allowed_relation_mappings",
        "forbidden_surface_attributes",
        "target_constraints",
        "mapping_method",
        "baselines",
        "negative_controls",
        "metrics",
        "upstream_c",
        "candidate_inferences",
        "provenance",
        "review",
    }
)
_GRAPH_FIELDS = frozenset({"nodes", "relations"})
_NODE_FIELDS = frozenset({"id", "role"})
_RELATION_FIELDS = frozenset({"source", "predicate", "target"})
_MAPPING_FIELDS = frozenset({"source_predicate", "target_predicate"})
_UPSTREAM_FIELDS = frozenset({"evidence_sufficient", "human_accepted", "selected_bridge_id"})
_PROVENANCE_FIELDS = frozenset({"generated_by", "source_artifact_digests"})
_REVIEW_FIELDS = frozenset(
    {"status", "human_reviewer", "human_approved_at_utc", "approved_proposal_digest"}
)


def validate_operator_d_mapping_contract(
    contract: Mapping[str, StructuredInput],
) -> dict[str, StructuredValue]:
    validated = _mapping(contract, "operator D mapping contract")
    _exact_fields(validated, _CONTRACT_FIELDS, "operator D mapping contract")
    _schema_version(validated.get("schema_version"), "operator D mapping contract schema_version")
    if validated.get("record_type") != "operator_d_mapping_proposal":
        raise ValueError("operator D mapping contract record_type is invalid")
    if validated.get("template_only") is not True:
        raise ValueError("operator D mapping contract template_only must be true")
    _require_false(validated, "runtime_authorized")
    if validated.get("requires_upstream_c_bridge") is not True:
        raise ValueError("operator D mapping contract requires_upstream_c_bridge must be true")
    _require_false(validated, "upstream_c_bridge_sufficient")
    if validated.get("zero_policy_violation_required") is not True:
        raise ValueError("operator D mapping contract zero_policy_violation_required must be true")
    if validated.get("approval_digest_field") != "approved_proposal_digest":
        raise ValueError("operator D mapping contract approval_digest_field is invalid")
    _exact_string_set(
        validated.get("allowed_mapping_methods"),
        _ALLOWED_MAPPING_METHODS,
        "allowed_mapping_methods",
    )
    _exact_string_set(
        validated.get("forbidden_mapping_methods"),
        _FORBIDDEN_MAPPING_METHODS,
        "forbidden_mapping_methods",
    )
    _exact_string_set(
        validated.get("forbidden_surface_attributes"),
        _FORBIDDEN_SURFACE_ATTRIBUTES,
        "forbidden_surface_attributes",
    )
    _exact_string_set(
        validated.get("required_baselines"), _REQUIRED_BASELINES, "required_baselines"
    )
    _exact_string_set(
        validated.get("required_negative_controls"),
        _REQUIRED_NEGATIVE_CONTROLS,
        "required_negative_controls",
    )
    _exact_string_set(validated.get("required_metrics"), _REQUIRED_METRICS, "required_metrics")
    _string_list(validated.get("admission_rules"), "admission_rules")
    _string_list(validated.get("method_references"), "method_references")
    return contract_validation.normalize_mapping(validated)


def validate_operator_d_mapping_proposal(
    proposal: Mapping[str, StructuredInput],
    *,
    contract: Mapping[str, StructuredInput],
    trusted_approvals: frozenset[TrustedOperatorApproval] = frozenset(),
) -> dict[str, StructuredValue]:
    rules = validate_operator_d_mapping_contract(contract)
    validated = _mapping(proposal, "operator D mapping proposal")
    _exact_fields(validated, _PROPOSAL_FIELDS, "operator D mapping proposal")
    _schema_version(validated.get("schema_version"), "operator D mapping proposal schema_version")
    if validated.get("authorization_state") != "report_only":
        raise ValueError("authorization_state must be report_only")
    _require_false(validated, "runtime_authorized")
    _required_string(validated, "proposal_id")
    source_policy = _required_string(validated, "source_domain_policy_id")
    target_policy = _required_string(validated, "target_domain_policy_id")
    if source_policy == target_policy:
        raise ValueError("Operator D requires distinct source and target domain policies")
    _required_string(validated, "source_record_id")
    _required_string(validated, "target_record_id")
    source_predicates = _graph(validated.get("source_graph"), "source_graph")
    target_predicates = _graph(validated.get("target_graph"), "target_graph")
    forbidden = set(
        _string_list(validated.get("forbidden_surface_attributes"), "forbidden_surface_attributes")
    )
    required_forbidden = set(
        _string_list(rules["forbidden_surface_attributes"], "forbidden_surface_attributes")
    )
    if forbidden != required_forbidden:
        raise ValueError("forbidden_surface_attributes do not match the contract")
    mappings = _mapping_list(
        validated.get("allowed_relation_mappings"), "allowed_relation_mappings"
    )
    for mapping in mappings:
        _exact_fields(mapping, _MAPPING_FIELDS, "allowed_relation_mappings")
        source_predicate = _required_string(mapping, "source_predicate")
        target_predicate = _required_string(mapping, "target_predicate")
        if target_predicate in forbidden or source_predicate in forbidden:
            raise ValueError("allowed_relation_mappings cannot use a forbidden surface attribute")
        if source_predicate not in source_predicates:
            raise ValueError("allowed_relation_mappings source_predicate is unbound")
        if target_predicate not in target_predicates:
            raise ValueError("allowed_relation_mappings target_predicate is unbound")
    target_constraints = set(
        _string_list(validated.get("target_constraints"), "target_constraints")
    )
    if not _REQUIRED_TARGET_CONSTRAINTS.issubset(target_constraints):
        raise ValueError("target_constraints must preserve policy leakage guards")
    mapping_method = _required_string(validated, "mapping_method")
    if mapping_method in set(
        _string_list(rules["forbidden_mapping_methods"], "forbidden_mapping_methods")
    ):
        raise ValueError("surface similarity cannot be the selected Operator D mapping method")
    if mapping_method not in set(
        _string_list(rules["allowed_mapping_methods"], "allowed_mapping_methods")
    ):
        raise ValueError("mapping_method is invalid")
    for field in ("baselines", "negative_controls", "metrics"):
        values = _string_list(validated.get(field), field)
        required = set(_string_list(rules[f"required_{field}"], f"required_{field}"))
        if not required.issubset(values):
            raise ValueError(f"{field} must include the contract-required values")
    upstream = _mapping(validated.get("upstream_c"), "upstream_c")
    _exact_fields(upstream, _UPSTREAM_FIELDS, "upstream_c")
    if (
        upstream.get("evidence_sufficient") is not False
        or upstream.get("human_accepted") is not False
        or upstream.get("selected_bridge_id") is not None
    ):
        raise ValueError("upstream C bridge remains insufficient and unaccepted")
    inferences = validated.get("candidate_inferences")
    if type(inferences) is not list or inferences:
        raise ValueError("candidate_inferences must remain empty without an upstream C bridge")
    provenance = _mapping(validated.get("provenance"), "provenance")
    _exact_fields(provenance, _PROVENANCE_FIELDS, "provenance")
    generated_by = _required_string(provenance, "generated_by")
    _sha256_list(provenance.get("source_artifact_digests"), "source_artifact_digests")
    review = _mapping(validated.get("review"), "review")
    _exact_fields(review, _REVIEW_FIELDS, "review")
    status = _required_string(review, "status")
    if status not in {"pending", "rejected", "human_approved"}:
        raise ValueError("review status is invalid")
    if status == "human_approved":
        require_operator_d_approval(
            review,
            generated_by=generated_by,
            expected_digest=operator_d_mapping_proposal_digest(validated),
            trusted_approvals=trusted_approvals,
        )
    elif any(
        review.get(field) is not None
        for field in ("human_reviewer", "human_approved_at_utc", "approved_proposal_digest")
    ):
        raise ValueError("unapproved review fields must be null")
    return contract_validation.normalize_mapping(validated)


def operator_d_mapping_proposal_digest(proposal: Mapping[str, StructuredInput]) -> str:
    preimage = copy.deepcopy(_mapping(proposal, "operator D mapping proposal"))
    review = contract_validation.mutable_mapping(preimage.get("review"))
    if review is not None:
        review["approved_proposal_digest"] = None
    return sha256_hex(canonical_json(preimage))


def _graph(value: StructuredInput, field: str) -> set[str]:
    graph = _mapping(value, field)
    _exact_fields(graph, _GRAPH_FIELDS, field)
    nodes = _mapping_list(graph.get("nodes"), f"{field} nodes")
    node_ids: list[str] = []
    for node in nodes:
        _exact_fields(node, _NODE_FIELDS, f"{field} nodes")
        node_ids.append(_required_string(node, "id"))
        _required_string(node, "role")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError(f"{field} nodes must have unique ids")
    known = set(node_ids)
    predicates: list[str] = []
    for relation in _mapping_list(graph.get("relations"), f"{field} relations"):
        _exact_fields(relation, _RELATION_FIELDS, f"{field} relations")
        source = _required_string(relation, "source")
        target = _required_string(relation, "target")
        if source not in known or target not in known:
            raise ValueError(f"{field} relations must reference graph nodes")
        predicates.append(_required_string(relation, "predicate"))
    return set(predicates)


def _require_false(value: Mapping[str, StructuredInput], field: str) -> None:
    if value.get(field) is not False:
        raise ValueError(f"{field} must be false")
