from __future__ import annotations

from dataclasses import dataclass

from nsqd.domain.operator_f_evaluation_metrics_basic import (
    confound_sensitivity,
    density,
    held_out_gain,
    quality_weighted_diversity,
    stability,
)
from nsqd.domain.operator_f_evaluation_metrics_stats import (
    interpretability,
    redundancy,
    residual_variation,
)
from nsqd.domain.operator_f_evaluation_types import (
    FoldDefinition,
    MetricResult,
    OperatorFSourceGroup,
    TrackReplay,
    TrustedInterpretabilityReview,
)


@dataclass(frozen=True, slots=True)
class MetricTrustContext:
    quality_weights: tuple[tuple[str, float], ...]
    interpretability_reviews: tuple[TrustedInterpretabilityReview, ...]
    fold_definition: FoldDefinition


def evaluate_metrics(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
    trust: MetricTrustContext,
) -> tuple[MetricResult, ...]:
    return (
        held_out_gain(records, tracks),
        density(records, tracks),
        quality_weighted_diversity(records, tracks, dict(trust.quality_weights)),
        stability(records, tracks),
        redundancy(records, tracks),
        residual_variation(records, tracks),
        confound_sensitivity(records, tracks),
        interpretability(records, trust.fold_definition, trust.interpretability_reviews),
    )
