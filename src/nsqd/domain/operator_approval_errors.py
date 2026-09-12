from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never


class ApprovalOperator(StrEnum):
    D = "operator_d_mapping_proposal"
    F = "operator_f_axis_proposal"
    G = "operator_g_failure_record"


class ApprovalErrorReason(StrEnum):
    INVALID_KIND = "invalid_kind"
    INVALID_CONTENT_DIGEST = "invalid_content_digest"
    INVALID_REVIEWER_IDENTITY = "invalid_reviewer_identity"
    INVALID_TRUSTED_APPROVAL_TIME = "invalid_trusted_approval_time"
    PARTIAL_TRUST_BINDING = "partial_trust_binding"
    INVALID_REVIEWER_SESSION = "invalid_reviewer_session"
    INVALID_APPROVAL_SCOPE = "invalid_approval_scope"
    INVALID_SUBMITTED_REVIEWER = "invalid_submitted_reviewer"
    D_REVIEWER_NOT_INDEPENDENT = "d_reviewer_not_independent"
    G_REVIEWER_NOT_INDEPENDENT = "g_reviewer_not_independent"
    D_REVIEWER_NOT_HUMAN = "d_reviewer_not_human"
    G_REVIEWER_NOT_HUMAN = "g_reviewer_not_human"
    INVALID_SUBMITTED_APPROVAL_TIME = "invalid_submitted_approval_time"
    G_REVIEWER_SESSION_NOT_INDEPENDENT = "g_reviewer_session_not_independent"
    G_APPROVAL_SCOPE_INVALID = "g_approval_scope_invalid"
    G_APPROVAL_PRECEDES_COMPLETION = "g_approval_precedes_completion"
    APPROVED_DIGEST_REQUIRED = "approved_digest_required"
    D_DIGEST_MISMATCH = "d_digest_mismatch"
    G_DIGEST_MISMATCH = "g_digest_mismatch"
    MISSING_TRUSTED_APPROVAL = "missing_trusted_approval"
    F_KIND_INVALID = "f_kind_invalid"
    F_DIGEST_MISMATCH = "f_digest_mismatch"
    F_REVIEWER_NOT_INDEPENDENT = "f_reviewer_not_independent"
    F_REVIEWER_NOT_HUMAN = "f_reviewer_not_human"
    F_REVIEWER_SESSION_NOT_INDEPENDENT = "f_reviewer_session_not_independent"
    F_APPROVAL_SCOPE_INVALID = "f_approval_scope_invalid"


class ApprovalErrorField(StrEnum):
    KIND = "kind"
    CONTENT_DIGEST = "content_digest"
    REVIEWER_IDENTITY = "reviewer_identity"
    APPROVED_AT_UTC = "approved_at_utc"
    HUMAN_REVIEWER = "human_reviewer"
    HUMAN_APPROVED_AT_UTC = "human_approved_at_utc"
    REVIEWER_SESSION = "reviewer_session"
    APPROVAL_SCOPE = "approval_scope"
    APPROVED_DIGEST = "approved_digest"
    TRUSTED_APPROVAL = "trusted_approval"


@dataclass(frozen=True, slots=True)
class OperatorApprovalError(ValueError):
    reason: ApprovalErrorReason

    def __post_init__(self) -> None:
        ValueError.__init__(self, _render_message(self.reason))

    @property
    def field(self) -> ApprovalErrorField:
        return _error_field(self.reason)

    def __str__(self) -> str:
        return _render_message(self.reason)


def reviewer_reason(operator: ApprovalOperator, *, independent: bool) -> ApprovalErrorReason:
    match operator:
        case ApprovalOperator.D:
            return (
                ApprovalErrorReason.D_REVIEWER_NOT_INDEPENDENT
                if independent
                else ApprovalErrorReason.D_REVIEWER_NOT_HUMAN
            )
        case ApprovalOperator.F:
            return (
                ApprovalErrorReason.F_REVIEWER_NOT_INDEPENDENT
                if independent
                else ApprovalErrorReason.F_REVIEWER_NOT_HUMAN
            )
        case ApprovalOperator.G:
            return (
                ApprovalErrorReason.G_REVIEWER_NOT_INDEPENDENT
                if independent
                else ApprovalErrorReason.G_REVIEWER_NOT_HUMAN
            )
        case unreachable:
            assert_never(unreachable)


def digest_reason(operator: ApprovalOperator) -> ApprovalErrorReason:
    match operator:
        case ApprovalOperator.D:
            return ApprovalErrorReason.D_DIGEST_MISMATCH
        case ApprovalOperator.F:
            return ApprovalErrorReason.F_DIGEST_MISMATCH
        case ApprovalOperator.G:
            return ApprovalErrorReason.G_DIGEST_MISMATCH
        case unreachable:
            assert_never(unreachable)


def _render_message(reason: ApprovalErrorReason) -> str:
    match reason:
        case ApprovalErrorReason.INVALID_KIND:
            return "approval kind is invalid"
        case ApprovalErrorReason.INVALID_CONTENT_DIGEST:
            return "content_digest must be a lowercase SHA-256 hex digest"
        case ApprovalErrorReason.INVALID_REVIEWER_IDENTITY:
            return "reviewer_identity must be a nonblank exact identity"
        case ApprovalErrorReason.INVALID_TRUSTED_APPROVAL_TIME:
            return "approved_at_utc must be timezone-aware UTC"
        case ApprovalErrorReason.PARTIAL_TRUST_BINDING:
            return "reviewer_session and approval_scope must be supplied together"
        case ApprovalErrorReason.INVALID_REVIEWER_SESSION:
            return "reviewer_session must be a nonblank exact value"
        case ApprovalErrorReason.INVALID_APPROVAL_SCOPE:
            return "approval_scope must be a nonblank exact value"
        case ApprovalErrorReason.INVALID_SUBMITTED_REVIEWER:
            return "human_reviewer must be a nonblank exact identity"
        case ApprovalErrorReason.D_REVIEWER_NOT_INDEPENDENT:
            return "Operator D approval requires an independent human reviewer"
        case ApprovalErrorReason.G_REVIEWER_NOT_INDEPENDENT:
            return "Operator G approval requires an independent human reviewer"
        case ApprovalErrorReason.D_REVIEWER_NOT_HUMAN:
            return "Operator D approval requires a human reviewer identity"
        case ApprovalErrorReason.G_REVIEWER_NOT_HUMAN:
            return "Operator G approval requires a human reviewer identity"
        case ApprovalErrorReason.INVALID_SUBMITTED_APPROVAL_TIME:
            return "human_approved_at_utc must be timezone-aware UTC"
        case ApprovalErrorReason.G_REVIEWER_SESSION_NOT_INDEPENDENT:
            return "Operator G approval requires an independent reviewer session"
        case ApprovalErrorReason.G_APPROVAL_SCOPE_INVALID:
            return "Operator G approval_scope must be operator_g_record_admission"
        case ApprovalErrorReason.G_APPROVAL_PRECEDES_COMPLETION:
            return "Operator G approval must not precede execution completion"
        case ApprovalErrorReason.APPROVED_DIGEST_REQUIRED:
            return "approved digest is required"
        case ApprovalErrorReason.D_DIGEST_MISMATCH:
            return "approved_proposal_digest does not match the mapping proposal"
        case ApprovalErrorReason.G_DIGEST_MISMATCH:
            return "approved_record_digest does not match the failure record"
        case ApprovalErrorReason.MISSING_TRUSTED_APPROVAL:
            return "approved operator metadata has no exact trusted approval"
        case ApprovalErrorReason.F_KIND_INVALID:
            return "Operator F approval kind must be operator_f_axis_proposal"
        case ApprovalErrorReason.F_DIGEST_MISMATCH:
            return "Operator F proposal digest does not match the axis proposal"
        case ApprovalErrorReason.F_REVIEWER_NOT_INDEPENDENT:
            return "Operator F approval requires an independent human reviewer"
        case ApprovalErrorReason.F_REVIEWER_NOT_HUMAN:
            return "Operator F approval requires a human reviewer identity"
        case ApprovalErrorReason.F_REVIEWER_SESSION_NOT_INDEPENDENT:
            return "Operator F approval requires an independent reviewer session"
        case ApprovalErrorReason.F_APPROVAL_SCOPE_INVALID:
            return "Operator F approval_scope must be evaluation_only"
        case unreachable:
            assert_never(unreachable)


def _error_field(reason: ApprovalErrorReason) -> ApprovalErrorField:
    match reason:
        case ApprovalErrorReason.INVALID_KIND | ApprovalErrorReason.F_KIND_INVALID:
            return ApprovalErrorField.KIND
        case ApprovalErrorReason.INVALID_CONTENT_DIGEST:
            return ApprovalErrorField.CONTENT_DIGEST
        case ApprovalErrorReason.INVALID_REVIEWER_IDENTITY:
            return ApprovalErrorField.REVIEWER_IDENTITY
        case ApprovalErrorReason.INVALID_TRUSTED_APPROVAL_TIME:
            return ApprovalErrorField.APPROVED_AT_UTC
        case (
            ApprovalErrorReason.INVALID_SUBMITTED_REVIEWER
            | ApprovalErrorReason.D_REVIEWER_NOT_INDEPENDENT
            | ApprovalErrorReason.G_REVIEWER_NOT_INDEPENDENT
            | ApprovalErrorReason.D_REVIEWER_NOT_HUMAN
            | ApprovalErrorReason.G_REVIEWER_NOT_HUMAN
            | ApprovalErrorReason.F_REVIEWER_NOT_INDEPENDENT
            | ApprovalErrorReason.F_REVIEWER_NOT_HUMAN
        ):
            return ApprovalErrorField.HUMAN_REVIEWER
        case ApprovalErrorReason.INVALID_SUBMITTED_APPROVAL_TIME:
            return ApprovalErrorField.HUMAN_APPROVED_AT_UTC
        case (
            ApprovalErrorReason.PARTIAL_TRUST_BINDING
            | ApprovalErrorReason.INVALID_REVIEWER_SESSION
            | ApprovalErrorReason.G_REVIEWER_SESSION_NOT_INDEPENDENT
            | ApprovalErrorReason.F_REVIEWER_SESSION_NOT_INDEPENDENT
        ):
            return ApprovalErrorField.REVIEWER_SESSION
        case (
            ApprovalErrorReason.INVALID_APPROVAL_SCOPE
            | ApprovalErrorReason.G_APPROVAL_SCOPE_INVALID
            | ApprovalErrorReason.F_APPROVAL_SCOPE_INVALID
        ):
            return ApprovalErrorField.APPROVAL_SCOPE
        case (
            ApprovalErrorReason.APPROVED_DIGEST_REQUIRED
            | ApprovalErrorReason.D_DIGEST_MISMATCH
            | ApprovalErrorReason.G_DIGEST_MISMATCH
            | ApprovalErrorReason.F_DIGEST_MISMATCH
        ):
            return ApprovalErrorField.APPROVED_DIGEST
        case ApprovalErrorReason.G_APPROVAL_PRECEDES_COMPLETION:
            return ApprovalErrorField.APPROVED_AT_UTC
        case ApprovalErrorReason.MISSING_TRUSTED_APPROVAL:
            return ApprovalErrorField.TRUSTED_APPROVAL
        case unreachable:
            assert_never(unreachable)
