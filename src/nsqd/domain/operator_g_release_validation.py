from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime

from nsqd.domain import contract_validation
from nsqd.domain.contract_validation import StructuredInput
from nsqd.domain.contract_validation_errors import (
    ContractValidationError,
    ContractValidationReason,
)
from nsqd.domain.operator_g_types import (
    PREDECLARED_OUTCOME_FIELDS,
    REGISTRATION_PREIMAGE_FIELDS,
    RESOURCE_CAP_FIELDS,
    V2_CONDITIONS_FIELDS,
    V2_OUTCOME_FIELDS,
    V2_RESTART_FIELDS,
    V2_TRIGGER_FIELDS,
)
from nsqd.domain.snapshot import canonical_json, sha256_hex


def operator_g_registration_digest(record: Mapping[str, StructuredInput]) -> str:
    validated = contract_validation.as_mapping(record, "Operator G failure record")
    preimage = {
        field: copy.deepcopy(validated[field])
        for field in REGISTRATION_PREIMAGE_FIELDS
        if field in validated
    }
    return sha256_hex(canonical_json(preimage))


def validate_registration(record: Mapping[str, StructuredInput]) -> datetime:
    contract_validation.required_string(record, "scientific_purpose")
    registered_at = contract_validation.utc_instant(
        record.get("registered_at_utc"), "registered_at_utc"
    )
    contract_validation.required_string(record, "exact_command")
    resource_cap = contract_validation.as_mapping(record.get("resource_cap"), "resource_cap")
    contract_validation.require_exact_fields(resource_cap, RESOURCE_CAP_FIELDS, "resource_cap")
    for field in RESOURCE_CAP_FIELDS:
        value = resource_cap.get(field)
        if type(value) is not int or value <= 0:
            raise ContractValidationError(
                ContractValidationReason.INVALID_VALUE, f"resource_cap.{field}"
            )
    outcomes = contract_validation.as_mapping(
        record.get("predeclared_success_failure_and_inconclusive_outcomes"),
        "predeclared_success_failure_and_inconclusive_outcomes",
    )
    contract_validation.require_exact_fields(
        outcomes,
        PREDECLARED_OUTCOME_FIELDS,
        "predeclared_success_failure_and_inconclusive_outcomes",
    )
    for field in PREDECLARED_OUTCOME_FIELDS:
        contract_validation.required_string(outcomes, field)
    registration_digest = record.get("registration_digest")
    if registration_digest != operator_g_registration_digest(record):
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "registration_digest")
    return registered_at


def validate_execution_outcome(
    record: Mapping[str, StructuredInput],
    failure_class_values: StructuredInput,
    registered_at: datetime,
) -> datetime:
    conditions = contract_validation.as_mapping(
        record.get("original_conditions"), "original_conditions"
    )
    contract_validation.require_exact_fields(
        conditions, V2_CONDITIONS_FIELDS, "original_conditions"
    )
    for field in ("code_revision", "configuration_digest", "model_or_method_identity"):
        contract_validation.required_string(conditions, field)
    contract_validation.sha256_list(conditions.get("data_snapshot_ids"), "data_snapshot_ids")
    started = contract_validation.utc_instant(conditions.get("started_at_utc"), "started_at_utc")
    completed = contract_validation.utc_instant(
        conditions.get("completed_at_utc"), "completed_at_utc"
    )
    if started < registered_at:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "started_at_utc")
    if completed < started:
        raise ContractValidationError(
            ContractValidationReason.COMPLETION_PRECEDES_START, "completed_at_utc"
        )
    outcome = contract_validation.as_mapping(record.get("outcome"), "outcome")
    contract_validation.require_exact_fields(outcome, V2_OUTCOME_FIELDS, "outcome")
    failure_classes = contract_validation.string_list(failure_class_values, "failure_class_values")
    failure_class = contract_validation.required_string(outcome, "failure_class")
    if failure_class not in failure_classes:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "failure_class")
    contract_validation.required_string(outcome, "bounded_observation")
    measured = contract_validation.finite_numeric_mapping(
        outcome.get("measured_results"), "measured_results"
    )
    contract_validation.sha256_list(
        outcome.get("evidence_artifact_digests"), "evidence_artifact_digests"
    )
    exit_status = record.get("exit_status")
    if type(exit_status) is not int:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "exit_status")
    measured_outcome = contract_validation.finite_numeric_mapping(
        record.get("measured_outcome"), "measured_outcome"
    )
    if measured_outcome != measured:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "measured_outcome")
    if record.get("failure_classification") != failure_class:
        raise ContractValidationError(
            ContractValidationReason.INVALID_VALUE, "failure_classification"
        )
    contract_validation.sha256_string(record.get("cleanup_receipt"), "cleanup_receipt")
    return completed


def validate_changed_and_restart_conditions(
    record: Mapping[str, StructuredInput], resurrection_scope_values: StructuredInput
) -> None:
    scopes = contract_validation.string_list(resurrection_scope_values, "resurrection_scope_values")
    triggers = contract_validation.mapping_list(
        record.get("changed_condition_triggers"), "changed_condition_triggers"
    )
    for trigger in triggers:
        contract_validation.require_exact_fields(
            trigger, V2_TRIGGER_FIELDS, "changed_condition_trigger"
        )
        for field in (
            "trigger_id",
            "predicate",
            "previous_condition",
            "new_condition",
            "measured_variable",
            "comparison_rule",
        ):
            contract_validation.required_string(trigger, field)
        contract_validation.sha256_list(
            trigger.get("evidence_artifact_digests"), "evidence_artifact_digests"
        )
        if trigger.get("resurrection_scope") not in scopes:
            raise ContractValidationError(
                ContractValidationReason.INVALID_VALUE, "resurrection_scope"
            )
    restarts = contract_validation.mapping_list(
        record.get("restart_conditions"), "restart_conditions"
    )
    for restart in restarts:
        contract_validation.require_exact_fields(restart, V2_RESTART_FIELDS, "restart_condition")
        contract_validation.required_string(restart, "condition_id")
        contract_validation.required_string(restart, "predicate")
        contract_validation.required_string(restart, "decision_owner")
        contract_validation.sha256_string(
            restart.get("required_evidence_digest"), "required_evidence_digest"
        )
        if restart.get("scope") not in scopes:
            raise ContractValidationError(
                ContractValidationReason.INVALID_VALUE, "restart condition scope"
            )
