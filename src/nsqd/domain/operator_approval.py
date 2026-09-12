from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, NotRequired, TypedDict, assert_never

from nsqd.domain.operator_approval_errors import (
    ApprovalErrorReason,
    ApprovalOperator,
    OperatorApprovalError,
    digest_reason,
    reviewer_reason,
)

OPERATOR_F_PROPOSAL_APPROVAL_SCOPE: Final = "evaluation_only"
type ApprovalScalar = str | datetime | int | float | bool | None
type ApprovalInput = ApprovalScalar | Sequence[ApprovalInput] | Mapping[str, ApprovalInput]


class OperatorDApprovalInput(TypedDict):
    human_reviewer: NotRequired[ApprovalInput]
    human_approved_at_utc: NotRequired[ApprovalInput]
    approved_proposal_digest: NotRequired[ApprovalInput]


class OperatorGApprovalInput(TypedDict):
    human_reviewer: NotRequired[ApprovalInput]
    human_approved_at_utc: NotRequired[ApprovalInput]
    approved_record_digest: NotRequired[ApprovalInput]
    reviewer_session: NotRequired[ApprovalInput]
    approval_scope: NotRequired[ApprovalInput]


class OperatorApprovalKind(StrEnum):
    D_MAPPING_PROPOSAL = "operator_d_mapping_proposal"
    F_AXIS_PROPOSAL = "operator_f_axis_proposal"
    G_FAILURE_RECORD = "operator_g_failure_record"


@dataclass(frozen=True, slots=True)
class TrustedOperatorApproval:
    kind: OperatorApprovalKind
    content_digest: str
    reviewer_identity: str
    approved_at_utc: datetime
    reviewer_session: str | None = None
    approval_scope: str | None = None

    def __post_init__(self) -> None:
        _validate_approval_fields(self)


@dataclass(frozen=True, slots=True)
class OperatorApprovalProducer:
    identity: str
    session: str


def require_operator_d_approval(
    review: OperatorDApprovalInput | Mapping[str, ApprovalInput],
    *,
    generated_by: str,
    expected_digest: str,
    trusted_approvals: frozenset[TrustedOperatorApproval],
) -> None:
    _require_submitted_approval(
        kind=OperatorApprovalKind.D_MAPPING_PROPOSAL,
        reviewer_value=review.get("human_reviewer"),
        approved_at_value=review.get("human_approved_at_utc"),
        digest_value=review.get("approved_proposal_digest"),
        generated_by=generated_by,
        expected_digest=expected_digest,
        trusted_approvals=trusted_approvals,
    )


def require_operator_f_proposal_approval(
    approval: TrustedOperatorApproval,
    *,
    producer: OperatorApprovalProducer,
    expected_digest: str,
) -> None:
    if approval.kind is not OperatorApprovalKind.F_AXIS_PROPOSAL:
        raise OperatorApprovalError(ApprovalErrorReason.F_KIND_INVALID)
    if approval.content_digest != expected_digest:
        raise OperatorApprovalError(ApprovalErrorReason.F_DIGEST_MISMATCH)
    if approval.reviewer_identity == producer.identity:
        raise OperatorApprovalError(ApprovalErrorReason.F_REVIEWER_NOT_INDEPENDENT)
    if not approval.reviewer_identity.startswith("human:"):
        raise OperatorApprovalError(ApprovalErrorReason.F_REVIEWER_NOT_HUMAN)
    if approval.reviewer_session is None or approval.reviewer_session == producer.session:
        raise OperatorApprovalError(ApprovalErrorReason.F_REVIEWER_SESSION_NOT_INDEPENDENT)
    if approval.approval_scope != OPERATOR_F_PROPOSAL_APPROVAL_SCOPE:
        raise OperatorApprovalError(ApprovalErrorReason.F_APPROVAL_SCOPE_INVALID)


def require_operator_g_approval(
    review: OperatorGApprovalInput | Mapping[str, ApprovalInput],
    *,
    generated_by: str,
    producer_session: str,
    completed_at_utc: datetime,
    expected_digest: str,
    trusted_approvals: frozenset[TrustedOperatorApproval],
) -> None:
    approved_at_value = review.get("human_approved_at_utc")
    match approved_at_value:
        case str():
            pass
        case datetime() | bool() | int() | float() | None | Sequence() | Mapping():
            raise OperatorApprovalError(ApprovalErrorReason.INVALID_SUBMITTED_APPROVAL_TIME)
        case unreachable:
            assert_never(unreachable)
    _require_submitted_approval(
        kind=OperatorApprovalKind.G_FAILURE_RECORD,
        reviewer_value=review.get("human_reviewer"),
        approved_at_value=approved_at_value,
        digest_value=review.get("approved_record_digest"),
        reviewer_session_value=review.get("reviewer_session"),
        approval_scope_value=review.get("approval_scope"),
        generated_by=generated_by,
        producer_session=producer_session,
        completed_at_utc=completed_at_utc,
        expected_digest=expected_digest,
        trusted_approvals=trusted_approvals,
    )


def _require_submitted_approval(
    *,
    kind: OperatorApprovalKind,
    reviewer_value: ApprovalInput,
    approved_at_value: ApprovalInput,
    digest_value: ApprovalInput,
    generated_by: str,
    expected_digest: str,
    trusted_approvals: frozenset[TrustedOperatorApproval],
    reviewer_session_value: ApprovalInput = None,
    approval_scope_value: ApprovalInput = None,
    producer_session: str | None = None,
    completed_at_utc: datetime | None = None,
) -> None:
    reviewer = _parse_reviewer_identity(reviewer_value)
    if reviewer == generated_by:
        raise OperatorApprovalError(reviewer_reason(ApprovalOperator(kind.value), independent=True))
    if not reviewer.startswith("human:"):
        raise OperatorApprovalError(
            reviewer_reason(ApprovalOperator(kind.value), independent=False)
        )
    approved_at = _parse_utc_approval_instant(approved_at_value)
    reviewer_session = _parse_optional_exact_string(
        reviewer_session_value, ApprovalErrorReason.INVALID_REVIEWER_SESSION
    )
    approval_scope = _parse_optional_exact_string(
        approval_scope_value, ApprovalErrorReason.INVALID_APPROVAL_SCOPE
    )
    match kind:
        case OperatorApprovalKind.G_FAILURE_RECORD:
            if reviewer_session is None or reviewer_session == producer_session:
                raise OperatorApprovalError(ApprovalErrorReason.G_REVIEWER_SESSION_NOT_INDEPENDENT)
            if approval_scope != "operator_g_record_admission":
                raise OperatorApprovalError(ApprovalErrorReason.G_APPROVAL_SCOPE_INVALID)
            if completed_at_utc is None or approved_at < completed_at_utc:
                raise OperatorApprovalError(ApprovalErrorReason.G_APPROVAL_PRECEDES_COMPLETION)
        case OperatorApprovalKind.D_MAPPING_PROPOSAL | OperatorApprovalKind.F_AXIS_PROPOSAL:
            pass
        case unreachable:
            assert_never(unreachable)
    approved_digest = _parse_approved_digest(digest_value)
    if approved_digest != expected_digest:
        raise OperatorApprovalError(digest_reason(ApprovalOperator(kind.value)))
    claim_key = (
        kind,
        approved_digest,
        reviewer,
        approved_at,
        reviewer_session,
        approval_scope,
    )
    if not any(
        claim_key
        == (
            approval.kind,
            approval.content_digest,
            approval.reviewer_identity,
            approval.approved_at_utc,
            approval.reviewer_session,
            approval.approval_scope,
        )
        for approval in trusted_approvals
    ):
        raise OperatorApprovalError(ApprovalErrorReason.MISSING_TRUSTED_APPROVAL)


def _parse_reviewer_identity(value: ApprovalInput) -> str:
    match value:
        case str() as reviewer if reviewer and reviewer == reviewer.strip():
            return reviewer
        case str() | datetime() | bool() | int() | float() | None | Sequence() | Mapping():
            raise OperatorApprovalError(ApprovalErrorReason.INVALID_SUBMITTED_REVIEWER)
        case unreachable:
            assert_never(unreachable)


def _parse_utc_approval_instant(value: ApprovalInput) -> datetime:
    match value:
        case str() as timestamp:
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as error:
                raise OperatorApprovalError(
                    ApprovalErrorReason.INVALID_SUBMITTED_APPROVAL_TIME
                ) from error
        case datetime() as timestamp:
            parsed = timestamp
        case bool() | int() | float() | None | Sequence() | Mapping():
            raise OperatorApprovalError(ApprovalErrorReason.INVALID_SUBMITTED_APPROVAL_TIME)
        case unreachable:
            assert_never(unreachable)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise OperatorApprovalError(ApprovalErrorReason.INVALID_SUBMITTED_APPROVAL_TIME)
    return parsed


def _parse_optional_exact_string(value: ApprovalInput, reason: ApprovalErrorReason) -> str | None:
    match value:
        case None:
            return None
        case str() as exact if exact and exact == exact.strip():
            return exact
        case str() | datetime() | bool() | int() | float() | Sequence() | Mapping():
            raise OperatorApprovalError(reason)
        case unreachable:
            assert_never(unreachable)


def _parse_approved_digest(value: ApprovalInput) -> str:
    match value:
        case str() as digest if digest and digest == digest.strip():
            return digest
        case str() | datetime() | bool() | int() | float() | None | Sequence() | Mapping():
            raise OperatorApprovalError(ApprovalErrorReason.APPROVED_DIGEST_REQUIRED)
        case unreachable:
            assert_never(unreachable)


def _validate_approval_fields(
    approval: TrustedOperatorApproval,
) -> None:
    if type(approval.kind) is not OperatorApprovalKind:
        raise OperatorApprovalError(ApprovalErrorReason.INVALID_KIND)
    if len(approval.content_digest) != 64 or any(
        character not in "0123456789abcdef" for character in approval.content_digest
    ):
        raise OperatorApprovalError(ApprovalErrorReason.INVALID_CONTENT_DIGEST)
    if (
        not approval.reviewer_identity
        or approval.reviewer_identity != approval.reviewer_identity.strip()
    ):
        raise OperatorApprovalError(ApprovalErrorReason.INVALID_REVIEWER_IDENTITY)
    if approval.approved_at_utc.tzinfo is None or approval.approved_at_utc.utcoffset() != timedelta(
        0
    ):
        raise OperatorApprovalError(ApprovalErrorReason.INVALID_TRUSTED_APPROVAL_TIME)
    if (approval.reviewer_session is None) != (approval.approval_scope is None):
        raise OperatorApprovalError(ApprovalErrorReason.PARTIAL_TRUST_BINDING)
    if approval.reviewer_session is not None:
        _parse_optional_exact_string(
            approval.reviewer_session, ApprovalErrorReason.INVALID_REVIEWER_SESSION
        )
        _parse_optional_exact_string(
            approval.approval_scope, ApprovalErrorReason.INVALID_APPROVAL_SCOPE
        )
