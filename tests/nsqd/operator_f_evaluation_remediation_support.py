from __future__ import annotations

import hashlib
import json

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_support import FOLD_SEED


def _sha256_json(value: operator_f.JsonValue) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def population_digest(records: tuple[operator_f.OperatorFSourceGroup, ...]) -> str:
    return _sha256_json(
        tuple(
            {
                "canonical_work_identity": record.canonical_work_identity,
                "approved_source_byte_sha256": record.approved_source_byte_sha256,
            }
            for record in sorted(records, key=lambda item: item.canonical_work_identity)
        )
    )


def fold_digest(records: tuple[operator_f.OperatorFSourceGroup, ...]) -> str:
    ranked = sorted(
        (
            hashlib.sha256(f"{FOLD_SEED}:{record.canonical_work_identity}".encode()).hexdigest(),
            record.canonical_work_identity,
        )
        for record in records
    )
    definition: dict[str, operator_f.JsonValue] = {
        "algorithm": "sha256_seeded_source_group_round_robin/v1",
        "seed": FOLD_SEED,
        "preimage": "utf8(seed + ':' + canonical_source_group_identity)",
        "ordering": "ascending_sha256_then_canonical_source_group_identity",
        "assignment": "zero_based_rank_modulo_5",
        "assignments": tuple(
            {
                "canonical_work_identity": identity,
                "digest": digest,
                "fold_index": rank % 5,
            }
            for rank, (digest, identity) in enumerate(ranked)
        ),
    }
    return _sha256_json(definition)


def quality_review(
    record: operator_f.OperatorFSourceGroup,
    weight: float = 1.0,
) -> operator_f.TrustedQualityReview:
    return operator_f.TrustedQualityReview(
        canonical_work_identity=record.canonical_work_identity,
        approved_source_byte_sha256=record.approved_source_byte_sha256,
        weight=weight,
        reviewer_identity=f"human:quality:{record.canonical_work_identity}",
        reviewer_session=f"quality-session:{record.canonical_work_identity}",
        blinded_to_fold_assignment=True,
        blinded_to_track_identity=True,
        blinded_to_candidate_label=True,
        blinded_to_numeric_outcomes=True,
        completed_before_split_assignment=True,
    )


def interpretability_reviews(
    records: tuple[operator_f.OperatorFSourceGroup, ...],
    ratings: tuple[int, int] = (1, 1),
) -> tuple[operator_f.TrustedInterpretabilityReview, ...]:
    population = population_digest(records)
    assignment = fold_digest(records)
    items = ("operational_definition", "replayable_assignment")
    return tuple(
        operator_f.TrustedInterpretabilityReview(
            source_population_digest=population,
            fold_assignment_digest=assignment,
            reviewer_identity=f"human:interpretability-{index}",
            reviewer_session=f"interpretability-session-{index}",
            blinded_to_source_identity=True,
            blinded_to_fold_assignment=True,
            blinded_to_numeric_outcomes=True,
            predeclared_rating_items=items,
            ratings=(
                operator_f.InterpretabilityRating(
                    name="operational_definition",
                    rating=rating,
                ),
                operator_f.InterpretabilityRating(name="replayable_assignment", rating=1),
            ),
        )
        for index, rating in enumerate(ratings)
    )


def records_in_fold_order(count: int) -> tuple[operator_f.OperatorFSourceGroup, ...]:
    from tests.nsqd.operator_f_evaluation_support import source_group

    records = tuple(source_group(index) for index in range(count))
    return tuple(
        record
        for _, record in sorted(
            (
                hashlib.sha256(
                    f"{FOLD_SEED}:{record.canonical_work_identity}".encode()
                ).hexdigest(),
                record,
            )
            for record in records
        )
    )
