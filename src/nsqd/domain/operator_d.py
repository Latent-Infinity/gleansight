from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from nsqd.domain.snapshot import canonical_json, is_utc_datetime_or_iso, sha256_hex

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
    {
        "status",
        "human_reviewer",
        "human_approved_at_utc",
        "approved_proposal_digest",
    }
)


def validate_operator_d_mapping_contract(contract: Mapping[str, object]) -> dict[str, Any]:
    validated = _mapping(contract, "operator D mapping contract")
    _exact_fields(validated, _CONTRACT_FIELDS, "operator D mapping contract")
    if validated.get("schema_version") != 1:
        raise ValueError("operator D mapping contract schema_version must be 1")
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
    _string_list(validated.get("allowed_mapping_methods"), "allowed_mapping_methods")
    _string_list(validated.get("forbidden_mapping_methods"), "forbidden_mapping_methods")
    if set(
        _string_list(validated.get("forbidden_surface_attributes"), "forbidden_surface_attributes")
    ) != set(_FORBIDDEN_SURFACE_ATTRIBUTES):
        raise ValueError("forbidden_surface_attributes do not match the contract")
    _string_list(validated.get("required_baselines"), "required_baselines")
    _string_list(validated.get("required_negative_controls"), "required_negative_controls")
    _string_list(validated.get("required_metrics"), "required_metrics")
    _string_list(validated.get("admission_rules"), "admission_rules")
    _string_list(validated.get("method_references"), "method_references")
    return validated


def validate_operator_d_mapping_proposal(
    proposal: Mapping[str, object],
    *,
    contract: Mapping[str, object],
) -> dict[str, Any]:
    rules = validate_operator_d_mapping_contract(contract)
    validated = _mapping(proposal, "operator D mapping proposal")
    _exact_fields(validated, _PROPOSAL_FIELDS, "operator D mapping proposal")
    if validated.get("schema_version") != rules["schema_version"]:
        raise ValueError("operator D mapping proposal schema_version does not match contract")
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
    _string_list(validated.get("target_constraints"), "target_constraints")
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
    if not isinstance(inferences, list) or inferences:
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
        reviewer = _required_string(review, "human_reviewer")
        if reviewer == generated_by:
            raise ValueError("Operator D approval requires an independent human reviewer")
        if not reviewer.startswith("human:"):
            raise ValueError("Operator D approval requires a human reviewer identity")
        if not is_utc_datetime_or_iso(review.get("human_approved_at_utc")):
            raise ValueError("human_approved_at_utc must be timezone-aware UTC")
        approved_digest = _required_string(review, "approved_proposal_digest")
        if approved_digest != operator_d_mapping_proposal_digest(validated):
            raise ValueError("approved_proposal_digest does not match the mapping proposal")
    elif any(
        review.get(field) is not None
        for field in ("human_reviewer", "human_approved_at_utc", "approved_proposal_digest")
    ):
        raise ValueError("unapproved review fields must be null")
    return validated


def operator_d_mapping_proposal_digest(proposal: Mapping[str, object]) -> str:
    preimage = copy.deepcopy(_mapping(proposal, "operator D mapping proposal"))
    review = preimage.get("review")
    if isinstance(review, dict):
        review["approved_proposal_digest"] = None
    return sha256_hex(canonical_json(preimage))


def _graph(value: object, field: str) -> set[str]:
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


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return {str(key): item for key, item in value.items()}


def _mapping_list(value: object, field: str) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    return [_mapping(item, field) for item in value]


def _exact_fields(value: Mapping[str, object], expected: frozenset[str], field: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{field} fields do not match the contract")


def _required_string(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{field} is required")
    return item.strip()


def _string_list(value: object, field: str) -> list[str]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(items) != len(value) or len(items) != len(set(items)):
        raise ValueError(f"{field} must contain unique non-empty strings")
    return items


def _sha256_list(value: object, field: str) -> list[str]:
    items = _string_list(value, field)
    if any(
        len(item) != 64 or any(char not in "0123456789abcdef" for char in item) for item in items
    ):
        raise ValueError(f"{field} must contain lowercase sha256 digests")
    return items


def _require_false(value: Mapping[str, object], field: str) -> None:
    if value.get(field) is not False:
        raise ValueError(f"{field} must be false")
