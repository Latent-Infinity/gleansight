from __future__ import annotations

from typing import Literal, Self

import pydantic

from nsqd.domain.operator_f_evaluation_validation import (
    BinaryInteger,
    NonBlank,
    NonnegativeFloat,
    OperatorFValidationError,
    Sha256,
    UtcInstant,
)


class _FrozenModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", strict=True)


class TrustedAdjudication(_FrozenModel):
    record_digest: Sha256
    reviewer_identity: NonBlank
    reviewer_session: NonBlank
    outcome: Literal["eligible"]


class TrustedCorpusApproval(_FrozenModel):
    record_digest: Sha256
    reviewer_identity: NonBlank
    reviewer_session: NonBlank
    approved_at_utc: UtcInstant
    approval_scope: Literal["evaluation_only"]


class TrustedSourceGroupApproval(_FrozenModel):
    canonical_work_identity: NonBlank
    observed_source_byte_sha256: Sha256
    adjudications: tuple[TrustedAdjudication, TrustedAdjudication]
    corpus_approval: TrustedCorpusApproval


class TrustedQualityReview(_FrozenModel):
    canonical_work_identity: NonBlank
    approved_source_byte_sha256: Sha256
    weight: NonnegativeFloat
    reviewer_identity: NonBlank
    reviewer_session: NonBlank
    blinded_to_fold_assignment: Literal[True]
    blinded_to_track_identity: Literal[True]
    blinded_to_candidate_label: Literal[True]
    blinded_to_numeric_outcomes: Literal[True]
    completed_before_split_assignment: Literal[True]


class InterpretabilityRating(_FrozenModel):
    name: NonBlank
    rating: BinaryInteger


class TrustedInterpretabilityReview(_FrozenModel):
    source_population_digest: Sha256
    fold_assignment_digest: Sha256
    reviewer_identity: NonBlank
    reviewer_session: NonBlank
    blinded_to_source_identity: Literal[True]
    blinded_to_fold_assignment: Literal[True]
    blinded_to_numeric_outcomes: Literal[True]
    predeclared_rating_items: tuple[NonBlank, ...]
    ratings: tuple[InterpretabilityRating, ...]

    @pydantic.model_validator(mode="after")
    def require_exact_predeclared_rating_items(self) -> Self:
        names = tuple(item.name for item in self.ratings)
        if not self.predeclared_rating_items:
            raise OperatorFValidationError("interpretability rating items must be predeclared")
        if len(names) != len(set(names)):
            raise OperatorFValidationError("interpretability rating items must be unique")
        if names != self.predeclared_rating_items:
            raise OperatorFValidationError("interpretability ratings must match predeclared items")
        return self
