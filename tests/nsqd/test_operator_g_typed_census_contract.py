from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from nsqd.domain.contract_validation_errors import (
    ContractValidationError,
    ContractValidationReason,
)
from nsqd.domain.operator_approval_errors import ApprovalErrorReason, OperatorApprovalError
from nsqd.domain.operator_g_census import (
    ReasonCode,
    RecordLocator,
    classify_failure_record,
)
from nsqd.domain.operator_g_readiness import readiness_source_bindings
from nsqd.infrastructure.operator_g_census_files import OUTPUT_DIRECTORIES
from tests.nsqd.operator_g_census_support import census_contract

REPO_ROOT = Path(__file__).resolve().parents[2]


def _classify_raised(error: ValueError) -> ReasonCode:
    with patch(
        "nsqd.domain.operator_g_census.validate_operator_g_failure_record",
        side_effect=error,
    ):
        candidate = classify_failure_record(
            {"failure_record_id": "candidate"},
            locator=RecordLocator("docs/candidate.json#0"),
            contract=census_contract(),
            trusted_approvals=frozenset(),
            trusted_evidence_artifacts=frozenset(),
            available_paths_by_digest={},
        )
    return candidate.reason_code


def test_missing_trusted_approval_reason_is_untrusted_when_rendered_text_changes() -> None:
    error = OperatorApprovalError(ApprovalErrorReason.MISSING_TRUSTED_APPROVAL)

    with patch(
        "nsqd.domain.operator_approval_errors._render_message",
        return_value="external authorization tuple absent",
    ):
        reason = _classify_raised(error)

    assert reason is ReasonCode.UNTRUSTED


def test_other_typed_approval_failure_is_malformed_even_when_text_mentions_trust() -> None:
    error = OperatorApprovalError(ApprovalErrorReason.G_APPROVAL_SCOPE_INVALID)

    with patch(
        "nsqd.domain.operator_approval_errors._render_message",
        return_value="trusted approval scope is malformed",
    ):
        reason = _classify_raised(error)

    assert reason is ReasonCode.MALFORMED


def test_contract_validation_failure_is_malformed() -> None:
    error = ContractValidationError(ContractValidationReason.INVALID_VALUE, "trusted approval")

    assert _classify_raised(error) is ReasonCode.MALFORMED


def test_unrelated_value_error_containing_trusted_approval_is_malformed() -> None:
    assert _classify_raised(ValueError("unrelated trusted approval parser failure")) is (
        ReasonCode.MALFORMED
    )


def test_readiness_source_bindings_cover_exact_operator_g_release_surface() -> None:
    source_roles = {
        binding.path: binding.role
        for binding in readiness_source_bindings(REPO_ROOT)
        if binding.path.startswith("src/")
    }

    assert source_roles == {
        "src/nsqd/domain/contract_validation.py": "shared_contract_validation",
        "src/nsqd/domain/contract_validation_errors.py": "typed_contract_validation_errors",
        "src/nsqd/domain/operator_approval.py": "external_approval_boundary",
        "src/nsqd/domain/operator_approval_errors.py": "typed_approval_errors",
        "src/nsqd/domain/operator_g.py": "canonical_failure_record_facade",
        "src/nsqd/domain/operator_g_census.py": "census_domain_algorithm",
        "src/nsqd/domain/operator_g_census_types.py": "census_domain_types",
        "src/nsqd/domain/operator_g_evidence.py": "evidence_trust_boundary",
        "src/nsqd/domain/operator_g_readiness.py": "readiness_projection_validator",
        "src/nsqd/domain/operator_g_readiness_projection.py": "readiness_projection_builder",
        "src/nsqd/domain/operator_g_record_validation.py": "canonical_failure_record_validation",
        "src/nsqd/domain/operator_g_release_validation.py": "release_failure_record_validation",
        "src/nsqd/domain/operator_g_types.py": "failure_record_contract_types",
        "src/nsqd/domain/operator_g_v1_validation.py": "legacy_record_validation",
        "src/nsqd/domain/snapshot.py": "canonical_snapshot_digest_runtime",
        "src/nsqd/infrastructure/operator_g_census.py": "bounded_census_orchestration",
        "src/nsqd/infrastructure/operator_g_census_files.py": "race_safe_filesystem_boundary",
        "src/nsqd/infrastructure/operator_g_census_formats.py": "structured_format_discovery",
        "src/nsqd/infrastructure/operator_g_structured_inputs.py": (
            "typed_structured_input_boundary"
        ),
    }


def test_contract_closure_is_the_only_exact_output_exclusion() -> None:
    assert OUTPUT_DIRECTORIES == frozenset(
        {"docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-schema-closure"}
    )
