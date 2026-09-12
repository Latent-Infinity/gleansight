from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from nsqd.domain import operator_approval
from nsqd.domain.operator_approval import (
    OperatorApprovalKind,
    OperatorApprovalProducer,
    TrustedOperatorApproval,
)

EXPECTED_DIGEST = "a" * 64
F_PROPOSAL_SCOPE = "evaluation_only"


def _approval(
    *,
    kind: OperatorApprovalKind | None = None,
    digest: str = EXPECTED_DIGEST,
    reviewer: str = "human:f-reviewer",
    reviewer_session: str | None = "session:f-reviewer",
    scope: str | None = F_PROPOSAL_SCOPE,
) -> TrustedOperatorApproval:
    return TrustedOperatorApproval(
        kind=kind or OperatorApprovalKind.F_AXIS_PROPOSAL,
        content_digest=digest,
        reviewer_identity=reviewer,
        approved_at_utc=datetime(2026, 9, 11, 12, tzinfo=UTC),
        reviewer_session=reviewer_session,
        approval_scope=scope,
    )


def _require(approval: TrustedOperatorApproval) -> None:
    operator_approval.require_operator_f_proposal_approval(
        approval,
        producer=OperatorApprovalProducer("agent:f-producer", "session:f-producer"),
        expected_digest=EXPECTED_DIGEST,
    )


def test_exact_detached_f_proposal_approval_is_accepted() -> None:
    # Given: an independently reviewed F proposal tuple
    approval = _approval()

    # When/Then: the shared boundary accepts the exact detached approval
    _require(approval)


@pytest.mark.parametrize(
    ("approval_factory", "message"),
    [
        (lambda: _approval(kind=OperatorApprovalKind.D_MAPPING_PROPOSAL), "kind"),
        (lambda: _approval(digest="b" * 64), "digest"),
        (lambda: _approval(reviewer_session=None, scope=None), "reviewer session"),
        (lambda: _approval(reviewer_session="session:f-producer"), "reviewer session"),
        (lambda: _approval(scope="runtime_authority"), "approval_scope"),
        (lambda: _approval(reviewer="agent:f-reviewer"), "human reviewer"),
        (lambda: _approval(reviewer="agent:f-producer"), "independent human"),
    ],
)
def test_detached_f_proposal_approval_rejects_wrong_tuple_fields(
    approval_factory: Callable[[], TrustedOperatorApproval], message: str
) -> None:
    # Given: detached F approval data with one invalid binding dimension
    approval = approval_factory()

    # When/Then: the shared boundary rejects that exact dimension
    with pytest.raises(ValueError, match=message):
        _require(approval)
