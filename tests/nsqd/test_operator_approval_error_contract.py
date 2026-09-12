from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from nsqd.domain.operator_approval import (
    OperatorApprovalKind,
    OperatorApprovalProducer,
    TrustedOperatorApproval,
    require_operator_d_approval,
    require_operator_f_proposal_approval,
    require_operator_g_approval,
)
from nsqd.domain.operator_approval_errors import (
    ApprovalErrorField,
    ApprovalErrorReason,
    ApprovalOperator,
    OperatorApprovalError,
    digest_reason,
    reviewer_reason,
)

DIGEST = "a" * 64
APPROVED_AT = datetime(2026, 9, 11, 12, tzinfo=UTC)
COMPLETED_AT = APPROVED_AT - timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class _FailureCase:
    invoke: Callable[[], TrustedOperatorApproval | None]
    message: str
    has_cause: bool = False


def _trusted(
    kind: OperatorApprovalKind = OperatorApprovalKind.G_FAILURE_RECORD,
    *,
    digest: str = DIGEST,
    reviewer: str = "human:reviewer",
    approved_at: datetime = APPROVED_AT,
    reviewer_session: str | None = "session:reviewer",
    approval_scope: str | None = "operator_g_record_admission",
) -> TrustedOperatorApproval:
    return TrustedOperatorApproval(
        kind,
        digest,
        reviewer,
        approved_at,
        reviewer_session,
        approval_scope,
    )


def _invalid_kind() -> TrustedOperatorApproval:
    invalid_kind = json.loads('"operator_g_failure_record"')
    return _trusted(invalid_kind)


def _require_d(
    *,
    reviewer: str | int | None = "human:reviewer",
    approved_at: str | datetime | int | None = APPROVED_AT,
    digest: str | int | None = DIGEST,
    trusted: frozenset[TrustedOperatorApproval] = frozenset(),
) -> None:
    require_operator_d_approval(
        {
            "human_reviewer": reviewer,
            "human_approved_at_utc": approved_at,
            "approved_proposal_digest": digest,
        },
        generated_by="agent:producer",
        expected_digest=DIGEST,
        trusted_approvals=trusted,
    )


def _require_g(
    *,
    reviewer: str = "human:reviewer",
    approved_at: str | datetime = "2026-09-11T12:00:00Z",
    reviewer_session: str | None = "session:reviewer",
    scope: str | None = "operator_g_record_admission",
    digest: str | None = DIGEST,
    producer_session: str = "session:producer",
    completed_at: datetime = COMPLETED_AT,
    trusted: frozenset[TrustedOperatorApproval] = frozenset(),
) -> None:
    require_operator_g_approval(
        {
            "human_reviewer": reviewer,
            "human_approved_at_utc": approved_at,
            "reviewer_session": reviewer_session,
            "approval_scope": scope,
            "approved_record_digest": digest,
        },
        generated_by="agent:producer",
        producer_session=producer_session,
        completed_at_utc=completed_at,
        expected_digest=DIGEST,
        trusted_approvals=trusted,
    )


def _require_f(approval: TrustedOperatorApproval) -> None:
    require_operator_f_proposal_approval(
        approval,
        producer=OperatorApprovalProducer("agent:producer", "session:producer"),
        expected_digest=DIGEST,
    )


@pytest.mark.parametrize(
    "case",
    [
        _FailureCase(_invalid_kind, "approval kind is invalid"),
        _FailureCase(
            lambda: _trusted(digest="A" * 64),
            "content_digest must be a lowercase SHA-256 hex digest",
        ),
        _FailureCase(
            lambda: _trusted(reviewer=" human:reviewer"),
            "reviewer_identity must be a nonblank exact identity",
        ),
        _FailureCase(
            lambda: _trusted(approved_at=datetime(2026, 9, 11, 12)),
            "approved_at_utc must be timezone-aware UTC",
        ),
        _FailureCase(
            lambda: _trusted(reviewer_session=None),
            "reviewer_session and approval_scope must be supplied together",
        ),
        _FailureCase(
            lambda: _trusted(reviewer_session=" session:reviewer"),
            "reviewer_session must be a nonblank exact value",
        ),
        _FailureCase(
            lambda: _trusted(approval_scope=" operator_g_record_admission"),
            "approval_scope must be a nonblank exact value",
        ),
        _FailureCase(
            lambda: _require_f(_trusted(OperatorApprovalKind.D_MAPPING_PROPOSAL)),
            "Operator F approval kind must be operator_f_axis_proposal",
        ),
        _FailureCase(
            lambda: _require_f(_trusted(OperatorApprovalKind.F_AXIS_PROPOSAL, digest="b" * 64)),
            "Operator F proposal digest does not match the axis proposal",
        ),
        _FailureCase(
            lambda: _require_d(reviewer=None, approved_at="bad", digest=None),
            "human_reviewer must be a nonblank exact identity",
        ),
        _FailureCase(
            lambda: _require_d(reviewer="agent:producer"),
            "Operator D approval requires an independent human reviewer",
        ),
        _FailureCase(
            lambda: _require_d(reviewer="agent:reviewer"),
            "Operator D approval requires a human reviewer identity",
        ),
        _FailureCase(
            lambda: _require_d(approved_at="bad"),
            "human_approved_at_utc must be timezone-aware UTC",
            has_cause=True,
        ),
        _FailureCase(
            lambda: _require_d(approved_at=1),
            "human_approved_at_utc must be timezone-aware UTC",
        ),
        _FailureCase(
            lambda: _require_d(approved_at=datetime(2026, 9, 11, 12)),
            "human_approved_at_utc must be timezone-aware UTC",
        ),
        _FailureCase(
            lambda: _require_d(digest="b" * 64),
            "approved_proposal_digest does not match the mapping proposal",
        ),
        _FailureCase(
            lambda: _require_g(approved_at=APPROVED_AT),
            "human_approved_at_utc must be timezone-aware UTC",
        ),
        _FailureCase(
            lambda: _require_g(reviewer_session=" session:reviewer"),
            "reviewer_session must be a nonblank exact value",
        ),
        _FailureCase(
            lambda: _require_g(scope="runtime_authority"),
            "Operator G approval_scope must be operator_g_record_admission",
        ),
        _FailureCase(
            lambda: _require_g(reviewer_session=None),
            "Operator G approval requires an independent reviewer session",
        ),
        _FailureCase(
            lambda: _require_g(completed_at=APPROVED_AT + timedelta(seconds=1)),
            "Operator G approval must not precede execution completion",
        ),
        _FailureCase(lambda: _require_g(digest=None), "approved digest is required"),
        _FailureCase(
            lambda: _require_g(),
            "approved operator metadata has no exact trusted approval",
        ),
    ],
)
def test_release_value_error_contract_preserves_message_args_cause_and_order(
    case: _FailureCase,
) -> None:
    with pytest.raises(ValueError) as captured:
        case.invoke()

    assert str(captured.value) == case.message
    assert captured.value.args == (case.message,)
    assert (captured.value.__cause__ is not None) is case.has_cause


def test_six_field_trusted_tuple_accepts_exact_g_approval() -> None:
    trusted = _trusted()

    _require_g(trusted=frozenset({trusted}))


def test_d_datetime_support_and_four_empty_binding_fields_remain_accepted() -> None:
    trusted = _trusted(
        OperatorApprovalKind.D_MAPPING_PROPOSAL,
        reviewer_session=None,
        approval_scope=None,
    )

    _require_d(trusted=frozenset({trusted}))


def test_release_boundary_failure_exposes_a_structured_reason() -> None:
    with pytest.raises(OperatorApprovalError) as captured:
        _require_g(scope="runtime_authority")

    assert captured.value.reason is ApprovalErrorReason.G_APPROVAL_SCOPE_INVALID


@pytest.mark.parametrize("reason", ApprovalErrorReason)
def test_every_reason_preserves_value_error_args_and_exposes_its_field(
    reason: ApprovalErrorReason,
) -> None:
    error = OperatorApprovalError(reason)

    assert error.args == (str(error),)
    assert isinstance(error.field, ApprovalErrorField)


@pytest.mark.parametrize("operator", ApprovalOperator)
@pytest.mark.parametrize("independent", [False, True])
def test_operator_specific_reason_selection_is_closed(
    operator: ApprovalOperator, independent: bool
) -> None:
    assert isinstance(reviewer_reason(operator, independent=independent), ApprovalErrorReason)
    assert isinstance(digest_reason(operator), ApprovalErrorReason)
