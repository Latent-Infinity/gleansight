from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime
from typing import assert_never

from nsqd.domain import contract_validation
from nsqd.domain.contract_validation import StructuredInput, StructuredValue
from nsqd.domain.contract_validation_errors import (
    ContractValidationError,
    ContractValidationReason,
)
from nsqd.domain.operator_approval import (
    OperatorGApprovalInput,
    TrustedOperatorApproval,
    require_operator_g_approval,
)
from nsqd.domain.operator_g_release_validation import (
    validate_changed_and_restart_conditions,
    validate_execution_outcome,
    validate_registration,
)
from nsqd.domain.operator_g_types import (
    CONTRACT_FIELDS,
    FAILURE_CLASS_VALUES,
    RECORD_OPTIONAL_FIELDS,
    RESURRECTION_SCOPE_VALUES,
    SOURCE_CLASS_VALUES,
    V1_RECORD_REQUIRED_FIELDS,
    V1_REQUIRED_FIELD_GROUPS,
    V2_PROVENANCE_FIELDS,
    V2_RECORD_REQUIRED_FIELDS,
    V2_REQUIRED_FIELD_GROUPS,
    V2_REVIEW_FIELDS,
    FailureRecordSchemaVersion,
    ReviewStatus,
)
from nsqd.domain.operator_g_v1_validation import validate_v1_failure_record
from nsqd.domain.snapshot import canonical_json, sha256_hex


def validate_operator_g_failure_contract(
    contract: Mapping[str, StructuredInput],
) -> dict[str, StructuredValue]:
    validated = contract_validation.as_mapping(contract, "Operator G failure contract")
    contract_validation.require_exact_fields(
        validated, CONTRACT_FIELDS, "Operator G failure contract"
    )
    schema_version = _schema_version(validated.get("schema_version"))
    if validated.get("record_type") != "approved_failed_experiment":
        raise ContractValidationError(
            ContractValidationReason.INVALID_VALUE, "Operator G failure contract record_type"
        )
    if validated.get("template_only") is not True:
        raise ContractValidationError(
            ContractValidationReason.MUST_BE_TRUE, "Operator G failure contract template_only"
        )
    if validated.get("operator_g_eligible_by_default") is not False:
        raise ContractValidationError(
            ContractValidationReason.INELIGIBLE_BY_DEFAULT, "Operator G failure contract"
        )
    required_fields = contract_validation.as_mapping(
        validated.get("required_fields"), "required_fields"
    )
    expected_groups = V1_REQUIRED_FIELD_GROUPS if schema_version == 1 else V2_REQUIRED_FIELD_GROUPS
    if set(required_fields) != set(expected_groups):
        raise ContractValidationError(
            ContractValidationReason.REQUIRED_FIELD_GROUPS_MISMATCH, "required_fields"
        )
    for group, expected in expected_groups.items():
        field = f"required_fields.{group}"
        if set(contract_validation.string_list(required_fields.get(group), field)) != expected:
            raise ContractValidationError(ContractValidationReason.VALUE_SET_MISMATCH, field)
    for field, expected in (
        ("failure_class_values", FAILURE_CLASS_VALUES),
        ("source_class_values", SOURCE_CLASS_VALUES),
        ("resurrection_scope_values", RESURRECTION_SCOPE_VALUES),
        ("optional_fields", RECORD_OPTIONAL_FIELDS),
    ):
        contract_validation.require_exact_string_set(validated.get(field), expected, field)
    for field in (
        "admission_rules",
        "operator_g_eligibility_rules",
        "forbidden_sources",
        "method_references",
    ):
        contract_validation.string_list(validated.get(field), field)
    return contract_validation.normalize_mapping(validated)


def validate_operator_g_failure_record(
    record: Mapping[str, StructuredInput],
    *,
    contract: Mapping[str, StructuredInput],
    trusted_approvals: frozenset[TrustedOperatorApproval] = frozenset(),
) -> dict[str, StructuredValue]:
    rules = validate_operator_g_failure_contract(contract)
    validated = contract_validation.as_mapping(record, "Operator G failure record")
    contract_version = _schema_version(rules.get("schema_version"))
    record_version = _schema_version(validated.get("schema_version"))
    if record_version != contract_version:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "schema_version")
    required_fields = (
        V1_RECORD_REQUIRED_FIELDS if record_version == 1 else V2_RECORD_REQUIRED_FIELDS
    )
    fields = set(validated)
    if not required_fields.issubset(fields) or not fields.issubset(
        required_fields | RECORD_OPTIONAL_FIELDS
    ):
        raise ContractValidationError(
            ContractValidationReason.FIELDS_MISMATCH, "Operator G failure record"
        )
    if validated.get("authorization_state") != "report_only":
        raise ContractValidationError(ContractValidationReason.REPORT_ONLY, "authorization_state")
    if validated.get("operator_g_eligible") is not False:
        raise ContractValidationError(
            ContractValidationReason.INDEPENDENT_AUTHORIZATION, "operator_g_eligible"
        )
    for field in ("failure_record_id", "domain_policy_id", "experiment_id"):
        contract_validation.required_string(validated, field)
    source_class = contract_validation.required_string(validated, "source_class")
    forbidden_sources = contract_validation.string_list(
        rules["forbidden_sources"], "forbidden_sources"
    )
    if source_class in forbidden_sources or source_class not in SOURCE_CLASS_VALUES:
        raise ContractValidationError(
            ContractValidationReason.DISALLOWED_SOURCE_CLASS, "source_class"
        )
    if "known_confounds" in validated:
        contract_validation.string_list(validated.get("known_confounds"), "known_confounds")
    if "supersedes_failure_record_id" in validated:
        supersedes = contract_validation.required_string(validated, "supersedes_failure_record_id")
        if supersedes == validated["failure_record_id"]:
            raise ContractValidationError(
                ContractValidationReason.SELF_REFERENCE, "supersedes_failure_record_id"
            )
    contract_validation.sha256_list(
        validated.get("immutable_source_artifact_digests"),
        "immutable_source_artifact_digests",
    )
    match record_version:
        case 1:
            validate_v1_failure_record(validated, rules)
        case 2:
            registered_at = validate_registration(validated)
            completed_at = validate_execution_outcome(
                validated, rules["failure_class_values"], registered_at
            )
            validate_changed_and_restart_conditions(validated, rules["resurrection_scope_values"])
            _validate_review(validated, trusted_approvals, completed_at)
        case unreachable:
            assert_never(unreachable)
    return contract_validation.normalize_mapping(validated)


def operator_g_failure_record_digest(record: Mapping[str, StructuredInput]) -> str:
    preimage = copy.deepcopy(contract_validation.as_mapping(record, "Operator G failure record"))
    review = contract_validation.mutable_mapping(preimage.get("review"))
    if review is not None:
        review["approved_record_digest"] = None
    return sha256_hex(canonical_json(preimage))


def _schema_version(value: StructuredInput | None) -> FailureRecordSchemaVersion:
    if type(value) is not int:
        raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "schema_version")
    match value:
        case 1:
            return 1
        case 2:
            return 2
        case int():
            raise ContractValidationError(ContractValidationReason.INVALID_VALUE, "schema_version")
        case unreachable:
            assert_never(unreachable)


def _validate_review(
    validated: Mapping[str, StructuredInput],
    trusted_approvals: frozenset[TrustedOperatorApproval],
    completed_at: datetime,
) -> None:
    provenance = contract_validation.as_mapping(validated.get("provenance"), "provenance")
    contract_validation.require_exact_fields(provenance, V2_PROVENANCE_FIELDS, "provenance")
    generated_by = contract_validation.required_string(provenance, "generated_by")
    producer_session = contract_validation.required_string(provenance, "producer_session")
    review = contract_validation.as_mapping(validated.get("review"), "review")
    contract_validation.require_exact_fields(review, V2_REVIEW_FIELDS, "review")
    raw_status = contract_validation.required_string(review, "review_status")
    try:
        status = ReviewStatus(raw_status)
    except ValueError as error:
        raise ContractValidationError(
            ContractValidationReason.INVALID_VALUE, "review_status"
        ) from error
    match status:
        case ReviewStatus.APPROVED:
            approval_review: OperatorGApprovalInput = {
                "human_reviewer": review.get("human_reviewer"),
                "human_approved_at_utc": review.get("human_approved_at_utc"),
                "approved_record_digest": review.get("approved_record_digest"),
                "reviewer_session": review.get("reviewer_session"),
                "approval_scope": review.get("approval_scope"),
            }
            require_operator_g_approval(
                approval_review,
                generated_by=generated_by,
                producer_session=producer_session,
                completed_at_utc=completed_at,
                expected_digest=operator_g_failure_record_digest(validated),
                trusted_approvals=trusted_approvals,
            )
        case ReviewStatus.PENDING | ReviewStatus.REJECTED:
            if any(
                review.get(field) is not None
                for field in (
                    "human_reviewer",
                    "reviewer_session",
                    "human_approved_at_utc",
                    "approval_scope",
                    "approved_record_digest",
                )
            ):
                raise ContractValidationError(
                    ContractValidationReason.UNAPPROVED_REVIEW_FIELDS, "review"
                )
        case unreachable:
            assert_never(unreachable)
