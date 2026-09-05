from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nsqd.domain.snapshot import canonical_json, is_utc_datetime_or_iso, sha256_hex

_PROPOSAL_FIELDS = frozenset(
    {
        "schema_version",
        "proposal_id",
        "authorization_state",
        "runtime_authorized",
        "schema_mutation_authorized",
        "domain_policy_id",
        "source_snapshot_ids",
        "existing_axis_inventory",
        "candidate_axis",
        "baselines",
        "negative_controls",
        "metrics",
        "provenance",
        "review",
    }
)
_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "template_only",
        "runtime_authorized",
        "schema_mutation_authorized",
        "maximum_candidate_axes_per_proposal",
        "descriptor_kind_values",
        "value_type_values",
        "required_baselines",
        "required_negative_controls",
        "required_metrics",
        "admission_rules",
        "method_references",
    }
)
_AXIS_FIELDS = frozenset(
    {
        "name",
        "descriptor_kind",
        "semantic_definition",
        "measurement_protocol",
        "observation_window",
        "value_type",
        "domain",
        "known_confounds",
        "leakage_risks",
    }
)
_REVIEW_FIELDS = frozenset({"status", "human_reviewer", "human_approved_at_utc", "approval_scope"})
_PROVENANCE_FIELDS = frozenset({"generated_by", "source_artifact_digests"})


def validate_operator_f_axis_contract(contract: Mapping[str, object]) -> dict[str, Any]:
    validated = _mapping(contract, "operator F axis contract")
    _exact_fields(validated, _CONTRACT_FIELDS, "operator F axis contract")
    if validated.get("schema_version") != 1:
        raise ValueError("operator F axis contract schema_version must be 1")
    if validated.get("record_type") != "operator_f_axis_proposal":
        raise ValueError("operator F axis contract record_type is invalid")
    for field in ("template_only", "runtime_authorized", "schema_mutation_authorized"):
        expected = field == "template_only"
        if validated.get(field) is not expected:
            raise ValueError(f"operator F axis contract {field} must be {str(expected).lower()}")
    if validated.get("maximum_candidate_axes_per_proposal") != 1:
        raise ValueError("operator F axis contract must allow exactly one candidate axis")
    _string_list(validated.get("descriptor_kind_values"), "descriptor_kind_values")
    _string_list(validated.get("value_type_values"), "value_type_values")
    _string_list(validated.get("required_baselines"), "required_baselines")
    _string_list(validated.get("required_negative_controls"), "required_negative_controls")
    _string_list(validated.get("required_metrics"), "required_metrics")
    _string_list(validated.get("admission_rules"), "admission_rules")
    _string_list(validated.get("method_references"), "method_references")
    return validated


def validate_operator_f_axis_proposal(
    proposal: Mapping[str, object],
    *,
    contract: Mapping[str, object],
) -> dict[str, Any]:
    rules = validate_operator_f_axis_contract(contract)
    validated = _mapping(proposal, "operator F axis proposal")
    _exact_fields(validated, _PROPOSAL_FIELDS, "operator F axis proposal")
    if validated.get("schema_version") != rules["schema_version"]:
        raise ValueError("operator F axis proposal schema_version does not match contract")
    if validated.get("authorization_state") != "report_only":
        raise ValueError("authorization_state must be report_only")
    _require_false(validated, "runtime_authorized")
    _require_false(validated, "schema_mutation_authorized")
    _required_string(validated, "proposal_id")
    _required_string(validated, "domain_policy_id")
    _sha256_list(validated.get("source_snapshot_ids"), "source_snapshot_ids")
    existing_axes = _string_list(
        validated.get("existing_axis_inventory"), "existing_axis_inventory"
    )

    axis = _mapping(validated.get("candidate_axis"), "candidate_axis")
    _exact_fields(axis, _AXIS_FIELDS, "candidate_axis")
    axis_name = _required_string(axis, "name")
    if axis_name in existing_axes:
        raise ValueError("candidate axis is already registered")
    if _required_string(axis, "descriptor_kind") not in rules["descriptor_kind_values"]:
        raise ValueError("candidate_axis descriptor_kind is invalid")
    if _required_string(axis, "value_type") not in rules["value_type_values"]:
        raise ValueError("candidate_axis value_type is invalid")
    for field in ("semantic_definition", "measurement_protocol", "observation_window"):
        _required_string(axis, field)
    _string_list(axis.get("domain"), "candidate_axis domain")
    _string_list(axis.get("known_confounds"), "candidate_axis known_confounds")
    _string_list(axis.get("leakage_risks"), "candidate_axis leakage_risks")

    for field in ("baselines", "negative_controls", "metrics"):
        values = _string_list(validated.get(field), field)
        required = set(_string_list(rules[f"required_{field}"], f"required_{field}"))
        if not required.issubset(values):
            raise ValueError(f"{field} must include the contract-required values")

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
            raise ValueError("Operator F approval requires an independent human reviewer")
        if not reviewer.startswith("human:"):
            raise ValueError("Operator F approval requires a human reviewer identity")
        if not is_utc_datetime_or_iso(review.get("human_approved_at_utc")):
            raise ValueError("human_approved_at_utc must be timezone-aware UTC")
        if review.get("approval_scope") not in {"schema_only", "evaluation_only"}:
            raise ValueError("approval_scope is invalid")
    return validated


def operator_f_axis_proposal_digest(proposal: Mapping[str, object]) -> str:
    return sha256_hex(canonical_json(_mapping(proposal, "operator F axis proposal")))


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return {str(key): item for key, item in value.items()}


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
