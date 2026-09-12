from __future__ import annotations

from enum import StrEnum


class CensusStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class CandidateClass(StrEnum):
    APPROVED_FAILURE_RECORD = "approved_failure_record"
    CONTRACT_TEMPLATE = "failure_record_contract_template"
    MALFORMED = "malformed_candidate"
    JOB_ERROR = "job_error"
    PENDING = "unapproved_failure_record"
    SUFFICIENCY_FAILURE = "sufficiency_failure"
    SYNTHETIC_FIXTURE = "synthetic_operator_g_test_fixture"
    TAU_MEASUREMENT = "tau_calibration_measurement"
    TEST_FAILURE = "pytest_or_contract_test_failure"
    UNEXECUTED_STUDY = "unexecuted_candidate_study"


class ReasonCode(StrEnum):
    CONFLICTING_ID = "conflicting_failure_record_id"
    CONTRACT_TEMPLATE = "contract_template_not_record"
    DUPLICATE = "duplicate_canonical_record_digest"
    FORBIDDEN_SOURCE = "forbidden_evidence_source"
    FORBIDDEN_JOB_ERROR = "forbidden_job_error_code"
    FORBIDDEN_SUFFICIENCY = "forbidden_sufficiency_failure"
    FORBIDDEN_TEST_FAILURE = "forbidden_test_failure_without_experiment_evidence"
    MALFORMED = "canonical_record_validation_failed"
    MISSING_EVIDENCE = "digest_bound_evidence_unavailable"
    QUALIFYING = "qualifying_approved_record"
    SYNTHETIC_PENDING = "synthetic_pending_fixture_not_artifact"
    TAU_NOT_EXPERIMENT = "tau_measurement_not_registered_experiment"
    UNEXECUTED = "unexecuted_study_no_measured_results"
    UNTRUSTED = "approved_metadata_without_independent_trust"
    UNAPPROVED = "record_not_approved"
