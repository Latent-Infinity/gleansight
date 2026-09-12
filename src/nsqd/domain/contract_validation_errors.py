from __future__ import annotations

from enum import StrEnum
from typing import assert_never


class ContractValidationReason(StrEnum):
    STRING_KEYED_MAPPING = "string_keyed_mapping"
    NON_EMPTY_LIST = "non_empty_list"
    FIELDS_MISMATCH = "fields_mismatch"
    REQUIRED_STRING = "required_string"
    UNIQUE_NON_EMPTY_STRINGS = "unique_non_empty_strings"
    INTEGER_ONE = "integer_one"
    VALUE_SET_MISMATCH = "value_set_mismatch"
    NON_EMPTY_MAPPING = "non_empty_mapping"
    FINITE_NUMERIC_MAPPING = "finite_numeric_mapping"
    LOWERCASE_SHA256_LIST = "lowercase_sha256_list"
    INVALID_VALUE = "invalid_value"
    MUST_BE_TRUE = "must_be_true"
    INELIGIBLE_BY_DEFAULT = "ineligible_by_default"
    REQUIRED_FIELD_GROUPS_MISMATCH = "required_field_groups_mismatch"
    REPORT_ONLY = "report_only"
    INDEPENDENT_AUTHORIZATION = "independent_authorization"
    DISALLOWED_SOURCE_CLASS = "disallowed_source_class"
    SELF_REFERENCE = "self_reference"
    UTC_INSTANT = "utc_instant"
    COMPLETION_PRECEDES_START = "completion_precedes_start"
    UNAPPROVED_REVIEW_FIELDS = "unapproved_review_fields"


class ContractValidationError(ValueError):
    __slots__ = ("field", "reason")

    reason: ContractValidationReason
    field: str

    def __init__(self, reason: ContractValidationReason, field: str) -> None:
        self.reason = reason
        self.field = field
        super().__init__(str(self))

    def __str__(self) -> str:
        match self.reason:
            case ContractValidationReason.STRING_KEYED_MAPPING:
                return f"{self.field} must be a string-keyed mapping"
            case ContractValidationReason.NON_EMPTY_LIST:
                return f"{self.field} must be a non-empty list"
            case ContractValidationReason.FIELDS_MISMATCH:
                return f"{self.field} fields do not match the contract"
            case ContractValidationReason.REQUIRED_STRING:
                return f"{self.field} is required"
            case ContractValidationReason.UNIQUE_NON_EMPTY_STRINGS:
                return f"{self.field} must contain unique non-empty strings"
            case ContractValidationReason.INTEGER_ONE:
                return f"{self.field} must be integer 1"
            case ContractValidationReason.VALUE_SET_MISMATCH:
                return f"{self.field} does not match the contract"
            case ContractValidationReason.NON_EMPTY_MAPPING:
                return f"{self.field} must not be empty"
            case ContractValidationReason.FINITE_NUMERIC_MAPPING:
                return f"{self.field} must contain finite numeric measurements"
            case ContractValidationReason.LOWERCASE_SHA256_LIST:
                return f"{self.field} must contain lowercase sha256 digests"
            case ContractValidationReason.INVALID_VALUE:
                return f"{self.field} is invalid"
            case ContractValidationReason.MUST_BE_TRUE:
                return f"{self.field} must be true"
            case ContractValidationReason.INELIGIBLE_BY_DEFAULT:
                return f"{self.field} must be ineligible by default"
            case ContractValidationReason.REQUIRED_FIELD_GROUPS_MISMATCH:
                return "required_fields groups do not match the contract"
            case ContractValidationReason.REPORT_ONLY:
                return f"{self.field} must be report_only"
            case ContractValidationReason.INDEPENDENT_AUTHORIZATION:
                return f"{self.field} must be false before independent authorization"
            case ContractValidationReason.DISALLOWED_SOURCE_CLASS:
                return "source_class is not an allowed experiment evidence source"
            case ContractValidationReason.SELF_REFERENCE:
                return "supersedes_failure_record_id cannot reference the same record"
            case ContractValidationReason.UTC_INSTANT:
                return f"{self.field} must be timezone-aware UTC"
            case ContractValidationReason.COMPLETION_PRECEDES_START:
                return "completed_at_utc must not precede started_at_utc"
            case ContractValidationReason.UNAPPROVED_REVIEW_FIELDS:
                return "unapproved review fields must be null"
            case unreachable:
                assert_never(unreachable)
