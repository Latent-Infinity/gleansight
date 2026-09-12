from __future__ import annotations

from collections.abc import Callable

import pytest

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_remediation_support import quality_review
from tests.nsqd.operator_f_evaluation_support import approval, inputs, source_group

type ApprovalMutation = Callable[
    [operator_f.OperatorFSourceGroup, operator_f.TrustedSourceGroupApproval],
    operator_f.TrustedSourceGroupApproval,
]


def _replace_first_approval(
    records: tuple[operator_f.OperatorFSourceGroup, ...],
    replacement: ApprovalMutation,
) -> tuple[operator_f.TrustedSourceGroupApproval, ...]:
    approvals = tuple(approval(record) for record in records)
    return (replacement(records[0], approvals[0]), *approvals[1:])


def _wrong_source_digest(
    _record: operator_f.OperatorFSourceGroup,
    trusted: operator_f.TrustedSourceGroupApproval,
) -> operator_f.TrustedSourceGroupApproval:
    return trusted.model_copy(update={"observed_source_byte_sha256": "f" * 64})


def _stale_digest(
    _record: operator_f.OperatorFSourceGroup,
    trusted: operator_f.TrustedSourceGroupApproval,
) -> operator_f.TrustedSourceGroupApproval:
    stale = trusted.adjudications[0].model_copy(update={"record_digest": "f" * 64})
    return trusted.model_copy(update={"adjudications": (stale, trusted.adjudications[1])})


def _self_reviewed(
    record: operator_f.OperatorFSourceGroup,
    trusted: operator_f.TrustedSourceGroupApproval,
) -> operator_f.TrustedSourceGroupApproval:
    self_review = trusted.adjudications[0].model_copy(
        update={"reviewer_identity": record.provenance.producer_identity}
    )
    return trusted.model_copy(update={"adjudications": (self_review, trusted.adjudications[1])})


def _nonhuman_review(
    _record: operator_f.OperatorFSourceGroup,
    trusted: operator_f.TrustedSourceGroupApproval,
) -> operator_f.TrustedSourceGroupApproval:
    nonhuman = trusted.adjudications[0].model_copy(update={"reviewer_identity": "agent:reviewer"})
    return trusted.model_copy(update={"adjudications": (nonhuman, trusted.adjudications[1])})


def _copied_approval(
    _record: operator_f.OperatorFSourceGroup,
    trusted: operator_f.TrustedSourceGroupApproval,
) -> operator_f.TrustedSourceGroupApproval:
    copied = approval(source_group(99))
    return copied.model_copy(update={"canonical_work_identity": trusted.canonical_work_identity})


def _producer_session_review(
    record: operator_f.OperatorFSourceGroup,
    trusted: operator_f.TrustedSourceGroupApproval,
) -> operator_f.TrustedSourceGroupApproval:
    same_session = trusted.adjudications[0].model_copy(
        update={"reviewer_session": record.provenance.producer_session}
    )
    return trusted.model_copy(update={"adjudications": (same_session, trusted.adjudications[1])})


@pytest.mark.parametrize(
    "replacement",
    [
        _wrong_source_digest,
        _stale_digest,
        _self_reviewed,
        _nonhuman_review,
        _copied_approval,
        _producer_session_review,
    ],
)
def test_invalid_approval_excludes_group_before_folds(replacement: ApprovalMutation) -> None:
    records = tuple(source_group(index) for index in range(6))
    approvals = _replace_first_approval(records, replacement)

    result = operator_f.evaluate_operator_f(inputs(records, approvals=approvals))

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert records[0].canonical_work_identity not in result.eligible_source_group_identities
    assert result.excluded_source_group_identities == (records[0].canonical_work_identity,)
    assert all(
        assignment.canonical_work_identity != records[0].canonical_work_identity
        for assignment in result.fold_definition.assignments
    )


def test_six_groups_with_one_absent_approval_evaluates_five() -> None:
    records = tuple(source_group(index) for index in range(6))
    approvals = tuple(approval(record) for record in records[1:])

    result = operator_f.evaluate_operator_f(inputs(records, approvals=approvals))

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert result.eligible_source_group_identities == tuple(
        record.canonical_work_identity for record in records[1:]
    )
    assert result.excluded_source_group_identities == (records[0].canonical_work_identity,)


def test_five_groups_with_one_absent_approval_returns_typed_unavailable() -> None:
    records = tuple(source_group(index) for index in range(5))
    approvals = tuple(approval(record) for record in records[1:])

    result = operator_f.evaluate_operator_f(inputs(records, approvals=approvals))

    assert isinstance(result, operator_f.OperatorFUnavailableResult)
    assert len(result.eligible_source_group_identities) == 4
    assert result.excluded_source_group_identities == (records[0].canonical_work_identity,)
    assert result.fold_definition.assignments == ()


def test_below_floor_bad_approvals_do_not_raise_or_create_folds() -> None:
    records = tuple(source_group(index) for index in range(4))
    approvals = _replace_first_approval(records, _wrong_source_digest)
    unknown_review = quality_review(source_group(99))

    result = operator_f.evaluate_operator_f(
        inputs(records, approvals=approvals, quality_reviews=(unknown_review,))
    )

    assert isinstance(result, operator_f.OperatorFUnavailableResult)
    assert len(result.eligible_source_group_identities) == 3
    assert result.fold_definition.assignments == ()


def test_mutation_after_approval_excludes_the_mutated_group() -> None:
    original = tuple(source_group(index) for index in range(6))
    approvals = tuple(approval(record) for record in original)
    mutated = original[0].model_copy(
        update={"primary_metric": operator_f.PrimaryMetric(name="mutated_after_approval")}
    )

    result = operator_f.evaluate_operator_f(inputs((mutated, *original[1:]), approvals=approvals))

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert mutated.canonical_work_identity not in result.eligible_source_group_identities


def test_excluded_records_and_unknown_quality_reviews_cannot_perturb_results() -> None:
    eligible = tuple(source_group(index) for index in range(5))
    trusted_eligible = inputs(eligible)
    baseline = operator_f.evaluate_operator_f(trusted_eligible)
    excluded = source_group(99, eligible=False)
    unknown = source_group(98)
    expanded = operator_f.evaluate_operator_f(
        inputs(
            (*eligible, excluded),
            approvals=(*trusted_eligible.trusted_approvals, approval(excluded)),
            quality_reviews=(quality_review(excluded), quality_review(unknown)),
        )
    )

    assert isinstance(baseline, operator_f.OperatorFReportResult)
    assert isinstance(expanded, operator_f.OperatorFReportResult)
    assert expanded.fold_definition == baseline.fold_definition
    assert expanded.shuffle == baseline.shuffle
    assert expanded.tracks == baseline.tracks
    assert expanded.metrics == baseline.metrics
