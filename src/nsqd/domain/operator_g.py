from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from nsqd.domain.snapshot import canonical_json, is_utc_datetime_or_iso, sha256_hex

_RECORD_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "failure_record_id",
        "authorization_state",
        "operator_g_eligible",
        "domain_policy_id",
        "experiment_id",
        "source_class",
        "immutable_source_artifact_digests",
        "original_conditions",
        "outcome",
        "changed_condition_triggers",
        "restart_conditions",
        "provenance",
        "review",
    }
)
_RECORD_OPTIONAL_FIELDS = frozenset({"known_confounds", "supersedes_failure_record_id"})
_SOURCE_CLASS_VALUES = frozenset({"registered_experiment_artifact"})
_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "template_only",
        "operator_g_eligible_by_default",
        "required_fields",
        "failure_class_values",
        "source_class_values",
        "resurrection_scope_values",
        "admission_rules",
        "operator_g_eligibility_rules",
        "optional_fields",
        "forbidden_sources",
        "method_references",
    }
)
_REQUIRED_FIELD_GROUPS = {
    "identity": frozenset(
        {
            "failure_record_id",
            "domain_policy_id",
            "experiment_id",
            "source_class",
            "immutable_source_artifact_digests",
        }
    ),
    "original_conditions": frozenset(
        {
            "code_revision",
            "data_snapshot_ids",
            "configuration_digest",
            "model_or_method_identity",
            "started_at_utc",
            "completed_at_utc",
        }
    ),
    "outcome": frozenset(
        {
            "failure_class",
            "bounded_observation",
            "measured_results",
            "evidence_artifact_digests",
        }
    ),
    "review": frozenset(
        {
            "review_status",
            "human_reviewer",
            "human_approved_at_utc",
            "approved_record_digest",
        }
    ),
}
_CONDITIONS_FIELDS = _REQUIRED_FIELD_GROUPS["original_conditions"]
_OUTCOME_FIELDS = _REQUIRED_FIELD_GROUPS["outcome"]
_TRIGGER_FIELDS = frozenset(
    {
        "trigger_id",
        "predicate",
        "previous_condition",
        "new_condition",
        "evidence_artifact_digests",
        "resurrection_scope",
    }
)
_RESTART_FIELDS = frozenset({"condition_id", "predicate", "scope"})
_PROVENANCE_FIELDS = frozenset({"generated_by"})
_REVIEW_FIELDS = _REQUIRED_FIELD_GROUPS["review"]


def validate_operator_g_failure_contract(contract: Mapping[str, object]) -> dict[str, Any]:
    validated = _mapping(contract, "Operator G failure contract")
    _exact_fields(validated, _CONTRACT_FIELDS, "Operator G failure contract")
    if validated.get("schema_version") != 1:
        raise ValueError("Operator G failure contract schema_version must be 1")
    if validated.get("record_type") != "approved_failed_experiment":
        raise ValueError("Operator G failure contract record_type is invalid")
    if validated.get("template_only") is not True:
        raise ValueError("Operator G failure contract template_only must be true")
    if validated.get("operator_g_eligible_by_default") is not False:
        raise ValueError("Operator G failure contract must be ineligible by default")
    required_fields = _mapping(validated.get("required_fields"), "required_fields")
    if set(required_fields) != set(_REQUIRED_FIELD_GROUPS):
        raise ValueError("required_fields groups do not match the contract")
    for group, expected in _REQUIRED_FIELD_GROUPS.items():
        if set(_string_list(required_fields.get(group), f"required_fields.{group}")) != expected:
            raise ValueError(f"required_fields.{group} does not match the contract")
    _string_list(validated.get("failure_class_values"), "failure_class_values")
    if set(_string_list(validated.get("source_class_values"), "source_class_values")) != set(
        _SOURCE_CLASS_VALUES
    ):
        raise ValueError("source_class_values do not match the contract")
    _string_list(validated.get("resurrection_scope_values"), "resurrection_scope_values")
    _string_list(validated.get("admission_rules"), "admission_rules")
    _string_list(validated.get("operator_g_eligibility_rules"), "operator_g_eligibility_rules")
    if set(_string_list(validated.get("optional_fields"), "optional_fields")) != set(
        _RECORD_OPTIONAL_FIELDS
    ):
        raise ValueError("optional_fields do not match the contract")
    _string_list(validated.get("forbidden_sources"), "forbidden_sources")
    _string_list(validated.get("method_references"), "method_references")
    return validated


def validate_operator_g_failure_record(
    record: Mapping[str, object],
    *,
    contract: Mapping[str, object],
) -> dict[str, Any]:
    rules = validate_operator_g_failure_contract(contract)
    validated = _mapping(record, "Operator G failure record")
    _required_and_optional_fields(
        validated,
        _RECORD_REQUIRED_FIELDS,
        _RECORD_OPTIONAL_FIELDS,
        "Operator G failure record",
    )
    if validated.get("schema_version") != rules["schema_version"]:
        raise ValueError("Operator G failure record schema_version does not match contract")
    if validated.get("authorization_state") != "report_only":
        raise ValueError("authorization_state must be report_only")
    if validated.get("operator_g_eligible") is not False:
        raise ValueError("operator_g_eligible must be false before independent authorization")
    for field in ("failure_record_id", "domain_policy_id", "experiment_id"):
        _required_string(validated, field)
    source_class = _required_string(validated, "source_class")
    forbidden_sources = _string_list(rules["forbidden_sources"], "forbidden_sources")
    if source_class in forbidden_sources or source_class not in _SOURCE_CLASS_VALUES:
        raise ValueError("source_class is not an allowed experiment evidence source")
    if "known_confounds" in validated:
        _string_list(validated.get("known_confounds"), "known_confounds")
    if "supersedes_failure_record_id" in validated:
        supersedes = _required_string(validated, "supersedes_failure_record_id")
        if supersedes == validated["failure_record_id"]:
            raise ValueError("supersedes_failure_record_id cannot reference the same record")
    _sha256_list(
        validated.get("immutable_source_artifact_digests"),
        "immutable_source_artifact_digests",
    )

    conditions = _mapping(validated.get("original_conditions"), "original_conditions")
    _exact_fields(conditions, _CONDITIONS_FIELDS, "original_conditions")
    for field in ("code_revision", "configuration_digest", "model_or_method_identity"):
        _required_string(conditions, field)
    _sha256_list(conditions.get("data_snapshot_ids"), "data_snapshot_ids")
    started = _utc(conditions.get("started_at_utc"), "started_at_utc")
    completed = _utc(conditions.get("completed_at_utc"), "completed_at_utc")
    if completed < started:
        raise ValueError("completed_at_utc must not precede started_at_utc")

    outcome = _mapping(validated.get("outcome"), "outcome")
    _exact_fields(outcome, _OUTCOME_FIELDS, "outcome")
    if _required_string(outcome, "failure_class") not in rules["failure_class_values"]:
        raise ValueError("failure_class is invalid")
    _required_string(outcome, "bounded_observation")
    _finite_numeric_mapping(outcome.get("measured_results"), "measured_results")
    _sha256_list(outcome.get("evidence_artifact_digests"), "evidence_artifact_digests")

    triggers = _mapping_list(
        validated.get("changed_condition_triggers"), "changed_condition_triggers"
    )
    for trigger in triggers:
        _exact_fields(trigger, _TRIGGER_FIELDS, "changed_condition_trigger")
        for field in ("trigger_id", "predicate", "previous_condition", "new_condition"):
            _required_string(trigger, field)
        _sha256_list(trigger.get("evidence_artifact_digests"), "evidence_artifact_digests")
        if trigger.get("resurrection_scope") not in rules["resurrection_scope_values"]:
            raise ValueError("resurrection_scope is invalid")
    restart_conditions = _mapping_list(validated.get("restart_conditions"), "restart_conditions")
    for restart in restart_conditions:
        _exact_fields(restart, _RESTART_FIELDS, "restart_condition")
        _required_string(restart, "condition_id")
        _required_string(restart, "predicate")
        if restart.get("scope") not in rules["resurrection_scope_values"]:
            raise ValueError("restart condition scope is invalid")

    provenance = _mapping(validated.get("provenance"), "provenance")
    _exact_fields(provenance, _PROVENANCE_FIELDS, "provenance")
    generated_by = _required_string(provenance, "generated_by")
    review = _mapping(validated.get("review"), "review")
    _exact_fields(review, _REVIEW_FIELDS, "review")
    status = _required_string(review, "review_status")
    if status not in {"pending", "rejected", "approved"}:
        raise ValueError("review_status is invalid")
    if status == "approved":
        reviewer = _required_string(review, "human_reviewer")
        if reviewer == generated_by:
            raise ValueError("Operator G approval requires an independent human reviewer")
        if not reviewer.startswith("human:"):
            raise ValueError("Operator G approval requires a human reviewer identity")
        _utc(review.get("human_approved_at_utc"), "human_approved_at_utc")
        approved_digest = _required_string(review, "approved_record_digest")
        if approved_digest != operator_g_failure_record_digest(validated):
            raise ValueError("approved_record_digest does not match the failure record")
    return validated


def operator_g_failure_record_digest(record: Mapping[str, object]) -> str:
    preimage = copy.deepcopy(_mapping(record, "Operator G failure record"))
    review = preimage.get("review")
    if isinstance(review, dict):
        review["approved_record_digest"] = None
    return sha256_hex(canonical_json(preimage))


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


def _required_and_optional_fields(
    value: Mapping[str, object],
    required: frozenset[str],
    optional: frozenset[str],
    field: str,
) -> None:
    fields = set(value)
    if not required.issubset(fields) or not fields.issubset(required | optional):
        raise ValueError(f"{field} fields do not match the contract")


def _finite_numeric_mapping(value: object, field: str) -> dict[str, float | int]:
    measured = _mapping(value, field)
    if not measured:
        raise ValueError(f"{field} must not be empty")
    if any(
        not isinstance(key, str)
        or not key.strip()
        or isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for key, item in measured.items()
    ):
        raise ValueError(f"{field} must contain finite numeric measurements")
    return measured


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


def _utc(value: object, field: str) -> datetime:
    if not is_utc_datetime_or_iso(value) or not isinstance(value, str):
        raise ValueError(f"{field} must be timezone-aware UTC")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
