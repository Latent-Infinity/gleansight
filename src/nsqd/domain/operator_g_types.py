from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from nsqd.domain.contract_validation import StructuredInput, StructuredValue

type OperatorGInput = dict[str, StructuredInput]
type OperatorGValue = dict[str, StructuredValue]
type FailureRecordSchemaVersion = Literal[1, 2]


class ReviewStatus(StrEnum):
    PENDING = "pending"
    REJECTED = "rejected"
    APPROVED = "approved"


V1_RECORD_REQUIRED_FIELDS: Final = frozenset(
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
V2_RECORD_REQUIRED_FIELDS: Final = frozenset(
    {
        "schema_version",
        "failure_record_id",
        "authorization_state",
        "operator_g_eligible",
        "domain_policy_id",
        "experiment_id",
        "scientific_purpose",
        "registered_at_utc",
        "registration_digest",
        "exact_command",
        "resource_cap",
        "predeclared_success_failure_and_inconclusive_outcomes",
        "source_class",
        "immutable_source_artifact_digests",
        "original_conditions",
        "outcome",
        "exit_status",
        "measured_outcome",
        "failure_classification",
        "changed_condition_triggers",
        "restart_conditions",
        "provenance",
        "review",
        "cleanup_receipt",
    }
)
RECORD_OPTIONAL_FIELDS: Final = frozenset({"known_confounds", "supersedes_failure_record_id"})
SOURCE_CLASS_VALUES: Final = frozenset({"registered_experiment_artifact"})
RESURRECTION_SCOPE_VALUES: Final = frozenset({"review_only", "test_only"})
FAILURE_CLASS_VALUES: Final = frozenset(
    ("implementation", "measurement", "method", "hypothesis", "regime_bound", "inconclusive")
)
CONTRACT_FIELDS: Final = frozenset(
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
V1_REQUIRED_FIELD_GROUPS: Final = {
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
        {"failure_class", "bounded_observation", "measured_results", "evidence_artifact_digests"}
    ),
    "review": frozenset(
        {"review_status", "human_reviewer", "human_approved_at_utc", "approved_record_digest"}
    ),
}
V2_REQUIRED_FIELD_GROUPS: Final = {
    **V1_REQUIRED_FIELD_GROUPS,
    "registration": frozenset(
        {
            "scientific_purpose",
            "registered_at_utc",
            "registration_digest",
            "exact_command",
            "resource_cap",
            "predeclared_success_failure_and_inconclusive_outcomes",
        }
    ),
    "execution": frozenset(
        {"exit_status", "measured_outcome", "failure_classification", "cleanup_receipt"}
    ),
    "changed_condition_trigger": frozenset(
        {
            "trigger_id",
            "predicate",
            "previous_condition",
            "new_condition",
            "evidence_artifact_digests",
            "resurrection_scope",
            "measured_variable",
            "comparison_rule",
        }
    ),
    "restart_condition": frozenset(
        {
            "condition_id",
            "predicate",
            "scope",
            "required_evidence_digest",
            "decision_owner",
        }
    ),
    "provenance": frozenset({"generated_by", "producer_session"}),
    "review": frozenset(
        {
            "review_status",
            "human_reviewer",
            "reviewer_session",
            "human_approved_at_utc",
            "approval_scope",
            "approved_record_digest",
        }
    ),
}
V1_CONDITIONS_FIELDS: Final = V1_REQUIRED_FIELD_GROUPS["original_conditions"]
V1_OUTCOME_FIELDS: Final = V1_REQUIRED_FIELD_GROUPS["outcome"]
V2_CONDITIONS_FIELDS: Final = V2_REQUIRED_FIELD_GROUPS["original_conditions"]
V2_OUTCOME_FIELDS: Final = V2_REQUIRED_FIELD_GROUPS["outcome"]
RESOURCE_CAP_FIELDS: Final = frozenset({"wall_clock_seconds", "memory_bytes", "cpu_cores"})
PREDECLARED_OUTCOME_FIELDS: Final = frozenset({"success", "failure", "inconclusive"})
V1_TRIGGER_FIELDS: Final = frozenset(
    {
        "trigger_id",
        "predicate",
        "previous_condition",
        "new_condition",
        "evidence_artifact_digests",
        "resurrection_scope",
    }
)
V2_TRIGGER_FIELDS: Final = frozenset(
    {
        "trigger_id",
        "predicate",
        "previous_condition",
        "new_condition",
        "evidence_artifact_digests",
        "resurrection_scope",
        "measured_variable",
        "comparison_rule",
    }
)
V1_RESTART_FIELDS: Final = frozenset({"condition_id", "predicate", "scope"})
V2_RESTART_FIELDS: Final = frozenset(
    {"condition_id", "predicate", "scope", "required_evidence_digest", "decision_owner"}
)
V1_PROVENANCE_FIELDS: Final = frozenset({"generated_by"})
V2_PROVENANCE_FIELDS: Final = frozenset({"generated_by", "producer_session"})
V1_REVIEW_FIELDS: Final = V1_REQUIRED_FIELD_GROUPS["review"]
V2_REVIEW_FIELDS: Final = V2_REQUIRED_FIELD_GROUPS["review"]
REGISTRATION_PREIMAGE_FIELDS: Final = frozenset(
    {
        "schema_version",
        "failure_record_id",
        "domain_policy_id",
        "experiment_id",
        "scientific_purpose",
        "registered_at_utc",
        "exact_command",
        "resource_cap",
        "predeclared_success_failure_and_inconclusive_outcomes",
    }
)
