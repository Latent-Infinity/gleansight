from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Final

from nsqd.domain import operator_f_evaluation as operator_f

FOLD_SEED: Final = "operator-f/evidence-resolution/source-grouped-five-fold/v1"
METRIC_NAMES: Final = (
    "held_out_gain",
    "density",
    "quality_weighted_diversity",
    "stability",
    "redundancy",
    "residual_variation",
    "confound_sensitivity",
    "interpretability",
)


def record_digest(record: operator_f.OperatorFSourceGroup) -> str:
    encoded = json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def source_group(
    index: int,
    *,
    eligible: bool = True,
    target: operator_f.ValidationTarget = "predictive_task",
    mechanism: str | None = None,
    confound_value: str | None = "a",
) -> operator_f.OperatorFSourceGroup:
    coordinates = None
    if eligible:
        coordinates = operator_f.RegisteredCoordinates(
            mechanism=mechanism or f"mechanism-{index % 2}",
            target=f"target-{index % 2}",
            horizon="daily",
        )
    strata = ()
    if confound_value is not None:
        strata = (operator_f.ConfoundStratum(name="venue", value=confound_value),)
    return operator_f.OperatorFSourceGroup(
        canonical_work_identity=f"doi:10.0000/work-{index}",
        all_version_identities=(f"doi:10.0000/work-{index}:v1",),
        approved_source_byte_sha256=f"{index % 10}" * 64,
        registered_coordinates=coordinates,
        validation_target=target if eligible else None,
        primary_metric=operator_f.PrimaryMetric(name="declared_metric"),
        provenance=operator_f.SourceProvenance(
            source_path=f"evidence/work-{index}.bin",
            producer_identity=f"producer:{index}",
            producer_session=f"producer-session:{index}",
            confound_strata=strata,
        ),
    )


def approval(
    record: operator_f.OperatorFSourceGroup,
    *,
    disagreement: bool = False,
) -> operator_f.TrustedSourceGroupApproval:
    digest = record_digest(record)
    second_digest = "f" * 64 if disagreement else digest
    return operator_f.TrustedSourceGroupApproval(
        canonical_work_identity=record.canonical_work_identity,
        observed_source_byte_sha256=record.approved_source_byte_sha256,
        adjudications=(
            operator_f.TrustedAdjudication(
                record_digest=digest,
                reviewer_identity=f"human:adjudicator-a:{record.canonical_work_identity}",
                reviewer_session=f"review-a:{record.canonical_work_identity}",
                outcome="eligible",
            ),
            operator_f.TrustedAdjudication(
                record_digest=second_digest,
                reviewer_identity=f"human:adjudicator-b:{record.canonical_work_identity}",
                reviewer_session=f"review-b:{record.canonical_work_identity}",
                outcome="eligible",
            ),
        ),
        corpus_approval=operator_f.TrustedCorpusApproval(
            record_digest=digest,
            reviewer_identity=f"human:corpus:{record.canonical_work_identity}",
            reviewer_session=f"corpus:{record.canonical_work_identity}",
            approved_at_utc="2026-09-09T00:00:00Z",
            approval_scope="evaluation_only",
        ),
    )


def inputs(
    records: Iterable[operator_f.OperatorFSourceGroup],
    *,
    approvals: tuple[operator_f.TrustedSourceGroupApproval, ...] | None = None,
    quality_reviews: tuple[operator_f.TrustedQualityReview, ...] = (),
    reviews: tuple[operator_f.TrustedInterpretabilityReview, ...] = (),
) -> operator_f.OperatorFEvaluationInputs:
    locked = tuple(records)
    trusted = tuple(approval(record) for record in locked) if approvals is None else approvals
    return operator_f.OperatorFEvaluationInputs(
        source_groups=locked,
        trusted_approvals=trusted,
        trusted_quality_reviews=quality_reviews,
        interpretability_reviews=reviews,
        imputation_authorized=False,
    )


def fold_oracle(identity: str) -> tuple[str, int]:
    digest = hashlib.sha256(f"{FOLD_SEED}:{identity}".encode()).hexdigest()
    return digest, -1


def balanced_inputs() -> operator_f.OperatorFEvaluationInputs:
    base = tuple(source_group(index) for index in range(20))
    ordered = sorted(
        base,
        key=lambda item: (
            fold_oracle(item.canonical_work_identity)[0],
            item.canonical_work_identity,
        ),
    )
    fold_positions: dict[int, int] = {}
    adjusted: list[operator_f.OperatorFSourceGroup] = []
    for rank, record in enumerate(ordered):
        fold_index = rank % 5
        position = fold_positions.get(fold_index, 0)
        fold_positions[fold_index] = position + 1
        target: operator_f.ValidationTarget = (
            "predictive_task" if position % 2 == 0 else "economic_utility"
        )
        adjusted.append(
            record.model_copy(
                update={
                    "registered_coordinates": operator_f.RegisteredCoordinates(
                        mechanism=f"mechanism-{position % 2}",
                        target=f"target-{position % 2}",
                        horizon=f"horizon-{position % 2}",
                    ),
                    "validation_target": target,
                    "provenance": record.provenance.model_copy(
                        update={
                            "confound_strata": (
                                operator_f.ConfoundStratum(
                                    name="venue", value="a" if position < 2 else "b"
                                ),
                            )
                        }
                    ),
                }
            )
        )
    from tests.nsqd.operator_f_evaluation_remediation_support import (
        interpretability_reviews,
        quality_review,
    )

    locked = tuple(adjusted)
    return inputs(
        locked,
        quality_reviews=tuple(quality_review(record) for record in locked),
        reviews=interpretability_reviews(locked),
    )


def result_digest(payload: dict[str, operator_f.JsonValue]) -> str:
    preimage = dict(payload)
    preimage["result_digest"] = None
    encoded = json.dumps(
        preimage,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
