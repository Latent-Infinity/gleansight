from __future__ import annotations

from collections.abc import Mapping
from typing import assert_never

from nsqd.domain import contract_validation
from nsqd.domain.contract_validation import StructuredInput
from nsqd.domain.contract_validation_errors import (
    ContractValidationError,
    ContractValidationReason,
)
from nsqd.domain.operator_g_types import (
    V1_CONDITIONS_FIELDS,
    V1_OUTCOME_FIELDS,
    V1_PROVENANCE_FIELDS,
    V1_RESTART_FIELDS,
    V1_REVIEW_FIELDS,
    V1_TRIGGER_FIELDS,
    ReviewStatus,
)


def validate_v1_failure_record(
    record: Mapping[str, StructuredInput], rules: Mapping[str, StructuredInput]
) -> None:
    conditions = contract_validation.as_mapping(
        record.get("original_conditions"), "original_conditions"
    )
    contract_validation.require_exact_fields(
        conditions, V1_CONDITIONS_FIELDS, "original_conditions"
    )
    for field in ("code_revision", "configuration_digest", "model_or_method_identity"):
        contract_validation.required_string(conditions, field)
    contract_validation.sha256_list(conditions.get("data_snapshot_ids"), "data_snapshot_ids")
    started = contract_validation.utc_instant(conditions.get("started_at_utc"), "started_at_utc")
    completed = contract_validation.utc_instant(
        conditions.get("completed_at_utc"), "completed_at_utc"
    )
    if completed < started:
        raise ContractValidationError(
            ContractValidationReason.COMPLETION_PRECEDES_START, "completed_at_utc"
        )

    outcome = contract_validation.as_mapping(record.get("outcome"), "outcome")
    contract_validation.require_exact_fields(outcome, V1_OUTCOME_FIELDS, "outcome")
    failure_classes = contract_validation.string_list(
        rules["failure_class_values"], "failure_class_values"
    )
    if contract_validation.required_string(outcome, "failure_class") not in failure_classes:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "failure_class")
    contract_validation.required_string(outcome, "bounded_observation")
    contract_validation.finite_numeric_mapping(outcome.get("measured_results"), "measured_results")
    contract_validation.sha256_list(
        outcome.get("evidence_artifact_digests"), "evidence_artifact_digests"
    )

    scopes = contract_validation.string_list(
        rules["resurrection_scope_values"], "resurrection_scope_values"
    )
    triggers = contract_validation.mapping_list(
        record.get("changed_condition_triggers"), "changed_condition_triggers"
    )
    for trigger in triggers:
        contract_validation.require_exact_fields(
            trigger, V1_TRIGGER_FIELDS, "changed_condition_trigger"
        )
        for field in ("trigger_id", "predicate", "previous_condition", "new_condition"):
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
        contract_validation.require_exact_fields(restart, V1_RESTART_FIELDS, "restart_condition")
        contract_validation.required_string(restart, "condition_id")
        contract_validation.required_string(restart, "predicate")
        if restart.get("scope") not in scopes:
            raise ContractValidationError(
                ContractValidationReason.INVALID_VALUE, "restart condition scope"
            )

    provenance = contract_validation.as_mapping(record.get("provenance"), "provenance")
    contract_validation.require_exact_fields(provenance, V1_PROVENANCE_FIELDS, "provenance")
    contract_validation.required_string(provenance, "generated_by")
    review = contract_validation.as_mapping(record.get("review"), "review")
    contract_validation.require_exact_fields(review, V1_REVIEW_FIELDS, "review")
    raw_status = contract_validation.required_string(review, "review_status")
    try:
        status = ReviewStatus(raw_status)
    except ValueError as error:
        raise ContractValidationError(
            ContractValidationReason.INVALID_VALUE, "review_status"
        ) from error
    match status:
        case ReviewStatus.APPROVED:
            raise ContractValidationError(
                ContractValidationReason.INVALID_VALUE, "schema_version 1 approved records"
            )
        case ReviewStatus.PENDING | ReviewStatus.REJECTED:
            if any(
                review.get(field) is not None
                for field in (
                    "human_reviewer",
                    "human_approved_at_utc",
                    "approved_record_digest",
                )
            ):
                raise ContractValidationError(
                    ContractValidationReason.UNAPPROVED_REVIEW_FIELDS, "review"
                )
        case unreachable:
            assert_never(unreachable)
