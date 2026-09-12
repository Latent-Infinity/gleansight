from __future__ import annotations

from nsqd.domain.operator_f_evaluation_support import OperatorFEvaluationError
from nsqd.domain.operator_f_evaluation_trust import (
    TrustedQualityReview,
    TrustedSourceGroupApproval,
)
from nsqd.domain.operator_f_evaluation_types import (
    FoldDefinition,
    OperatorFSourceGroup,
)
from nsqd.domain.snapshot import canonical_json, sha256_hex


def source_group_digest(record: OperatorFSourceGroup) -> str:
    return sha256_hex(canonical_json(record.model_dump(mode="json")))


def source_population_digest(records: tuple[OperatorFSourceGroup, ...]) -> str:
    payload = tuple(
        {
            "canonical_work_identity": record.canonical_work_identity,
            "approved_source_byte_sha256": record.approved_source_byte_sha256,
        }
        for record in sorted(records, key=lambda item: item.canonical_work_identity)
    )
    return sha256_hex(canonical_json(payload))


def fold_definition_digest(folds: FoldDefinition) -> str:
    return sha256_hex(canonical_json(folds.model_dump(mode="json")))


def partition_trusted_approval_eligibility(
    structurally_eligible: tuple[OperatorFSourceGroup, ...],
    approvals: tuple[TrustedSourceGroupApproval, ...],
) -> tuple[tuple[OperatorFSourceGroup, ...], tuple[OperatorFSourceGroup, ...]]:
    by_identity = {approval.canonical_work_identity: approval for approval in approvals}
    eligible: list[OperatorFSourceGroup] = []
    excluded: list[OperatorFSourceGroup] = []
    for record in structurally_eligible:
        approval = by_identity.get(record.canonical_work_identity)
        if approval is None:
            excluded.append(record)
            continue
        expected_digest = source_group_digest(record)
        adjudication_digests = tuple(item.record_digest for item in approval.adjudications)
        reviewers = tuple(item.reviewer_identity for item in approval.adjudications) + (
            approval.corpus_approval.reviewer_identity,
        )
        sessions = tuple(item.reviewer_session for item in approval.adjudications) + (
            approval.corpus_approval.reviewer_session,
        )
        independent_humans = (
            all(reviewer.startswith("human:") for reviewer in reviewers)
            and len(reviewers) == len(set(reviewers))
            and record.provenance.producer_identity not in reviewers
            and len(sessions) == len(set(sessions))
            and record.provenance.producer_session not in sessions
        )
        digest_bound = (
            approval.observed_source_byte_sha256 == record.approved_source_byte_sha256
            and len(set(adjudication_digests)) == 1
            and adjudication_digests[0] == expected_digest
            and approval.corpus_approval.record_digest == expected_digest
        )
        if independent_humans and digest_bound:
            eligible.append(record)
        else:
            excluded.append(record)
    return tuple(eligible), tuple(excluded)


def trusted_quality_weights(
    records: tuple[OperatorFSourceGroup, ...],
    reviews: tuple[TrustedQualityReview, ...],
) -> dict[str, float]:
    by_identity = {record.canonical_work_identity: record for record in records}
    producer_identities = {record.provenance.producer_identity for record in records}
    producer_sessions = {record.provenance.producer_session for record in records}
    weights: dict[str, float] = {}
    for review in reviews:
        record = by_identity.get(review.canonical_work_identity)
        if record is None:
            continue
        if review.approved_source_byte_sha256 != record.approved_source_byte_sha256:
            raise OperatorFEvaluationError("quality review source digest mismatch")
        independent = (
            review.reviewer_identity.startswith("human:")
            and review.reviewer_identity not in producer_identities
            and review.reviewer_session not in producer_sessions
        )
        if not independent:
            raise OperatorFEvaluationError("quality review requires an independent human reviewer")
        weights[review.canonical_work_identity] = review.weight
    return weights
