from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from nsqd.domain import operator_f_evaluation as operator_f
from nsqd.domain.operator_f_evaluation_metrics_basic import density
from nsqd.domain.operator_f_evaluation_support import build_folds, build_shuffle, build_tracks
from tests.nsqd.operator_f_evaluation_remediation_support import (
    quality_review,
    records_in_fold_order,
)
from tests.nsqd.operator_f_evaluation_support import inputs, source_group


def _metric(
    result: operator_f.OperatorFReportResult,
    name: operator_f.MetricName,
) -> operator_f.MetricResult:
    return next(metric for metric in result.metrics if metric.name == name)


def _series(metric: operator_f.MetricResult, track_id: str) -> operator_f.MetricSeries:
    return next(series for series in metric.series if series.track_id == track_id)


def test_density_remains_records_per_occupied_held_out_cell() -> None:
    records = tuple(
        source_group(index).model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism=f"mechanism-{index}",
                    target="shared",
                    horizon="shared",
                )
            }
        )
        for index in range(10)
    )
    folds = build_folds(records)
    labels = tuple(
        (record.canonical_work_identity, record.validation_target)
        for record in records
        if record.validation_target is not None
    )
    tracks = build_tracks(labels, folds, build_shuffle(tuple(identity for identity, _ in labels)))

    result = density(records, tracks)

    current = result.series[0]
    assert tuple(observation.value for observation in current.observations) == (1.0,) * 5
    assert current.aggregate_value == 1.0


def test_delimiter_characters_do_not_merge_distinct_occupied_cells() -> None:
    ordered = records_in_fold_order(10)
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism="a|b" if index < 5 else "a",
                    target="c" if index < 5 else "b|c",
                    horizon="d",
                )
            }
        )
        for index, record in enumerate(ordered)
    )
    reviews = tuple(quality_review(record, 1.0) for record in records)

    result = operator_f.evaluate_operator_f(inputs(records, quality_reviews=reviews))

    assert isinstance(result, operator_f.OperatorFReportResult)
    density_metric = _metric(result, "density")
    diversity_metric = _metric(result, "quality_weighted_diversity")
    assert tuple(item.value for item in density_metric.series[0].observations) == (1.0,) * 5
    assert tuple(item.value for item in diversity_metric.series[0].observations) == (1.0,) * 5
    assert tuple(item.value for item in density_metric.series[1].observations) == (1.0,) * 5
    assert tuple(item.value for item in diversity_metric.series[1].observations) == (1.0,) * 5


def test_quality_diversity_uses_maximum_weight_per_occupied_cell_and_candidate_split() -> None:
    ordered = records_in_fold_order(10)
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism=f"fold-{index % 5}",
                    target="shared",
                    horizon="shared",
                ),
                "validation_target": ("predictive_task" if index < 5 else "economic_utility"),
            }
        )
        for index, record in enumerate(ordered)
    )
    weights = tuple(
        quality_review(record, 1.0 if index < 5 else 3.0) for index, record in enumerate(records)
    )

    result = operator_f.evaluate_operator_f(inputs(records, quality_reviews=weights))

    assert isinstance(result, operator_f.OperatorFReportResult)
    metric = _metric(result, "quality_weighted_diversity")
    current = _series(metric, "current_registered_axes")
    candidate = _series(metric, "current_axes_plus_validation_target")
    assert tuple(observation.value for observation in current.observations) == (0.75,) * 5
    assert current.aggregate_value == 0.75
    assert tuple(observation.value for observation in candidate.observations) == (1.0,) * 5
    assert candidate.aggregate_value == 1.0


def test_quality_diversity_sums_cell_maxima_across_multiple_collisions() -> None:
    ordered = records_in_fold_order(20)
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism=f"cell-{index // 10}",
                    target=f"fold-{index % 5}",
                    horizon="shared",
                )
            }
        )
        for index, record in enumerate(ordered)
    )
    fold_weights = (1.0, 3.0, 2.0, 4.0)
    weights = tuple(
        quality_review(record, fold_weights[index // 5]) for index, record in enumerate(records)
    )

    result = operator_f.evaluate_operator_f(inputs(records, quality_reviews=weights))

    assert isinstance(result, operator_f.OperatorFReportResult)
    current = _series(_metric(result, "quality_weighted_diversity"), "current_registered_axes")
    assert tuple(observation.value for observation in current.observations) == (0.7,) * 5


def test_quality_diversity_is_invariant_to_record_permutation_and_weight_scaling() -> None:
    ordered = records_in_fold_order(10)
    shared = operator_f.RegisteredCoordinates(mechanism="same", target="same", horizon="same")
    records = tuple(
        record.model_copy(update={"registered_coordinates": shared}) for record in ordered
    )
    weights = tuple(
        quality_review(record, 1.0 if index < 5 else 3.0) for index, record in enumerate(records)
    )
    scaled = tuple(review.model_copy(update={"weight": review.weight * 11.0}) for review in weights)

    first = operator_f.evaluate_operator_f(inputs(records, quality_reviews=weights))
    second = operator_f.evaluate_operator_f(inputs(reversed(records), quality_reviews=scaled))

    assert isinstance(first, operator_f.OperatorFReportResult)
    assert isinstance(second, operator_f.OperatorFReportResult)
    first_values = tuple(
        observation.value
        for observation in _series(
            _metric(first, "quality_weighted_diversity"), "current_registered_axes"
        ).observations
    )
    second_values = tuple(
        observation.value
        for observation in _series(
            _metric(second, "quality_weighted_diversity"), "current_registered_axes"
        ).observations
    )
    assert first_values == second_values == (0.75,) * 5


def test_quality_diversity_is_invariant_at_the_largest_finite_weight_scale() -> None:
    ordered = records_in_fold_order(10)
    shared = operator_f.RegisteredCoordinates(mechanism="same", target="same", horizon="same")
    records = tuple(
        record.model_copy(update={"registered_coordinates": shared}) for record in ordered
    )
    ordinary = tuple(quality_review(record, 1.0) for record in records)
    extreme = tuple(quality_review(record, 1e308) for record in records)

    ordinary_result = operator_f.evaluate_operator_f(inputs(records, quality_reviews=ordinary))
    extreme_result = operator_f.evaluate_operator_f(inputs(records, quality_reviews=extreme))

    assert isinstance(ordinary_result, operator_f.OperatorFReportResult)
    assert isinstance(extreme_result, operator_f.OperatorFReportResult)
    ordinary_values = tuple(
        observation.value
        for observation in _series(
            _metric(ordinary_result, "quality_weighted_diversity"), "current_registered_axes"
        ).observations
    )
    extreme_values = tuple(
        observation.value
        for observation in _series(
            _metric(extreme_result, "quality_weighted_diversity"), "current_registered_axes"
        ).observations
    )
    assert ordinary_values == extreme_values == (0.5,) * 5


def test_missing_and_zero_quality_weights_remain_typed_unavailable() -> None:
    records = records_in_fold_order(10)
    missing = operator_f.evaluate_operator_f(inputs(records))
    zero_reviews = tuple(quality_review(record, 0.0) for record in records)
    zero = operator_f.evaluate_operator_f(inputs(records, quality_reviews=zero_reviews))

    assert isinstance(missing, operator_f.OperatorFReportResult)
    assert isinstance(zero, operator_f.OperatorFReportResult)
    assert _metric(missing, "quality_weighted_diversity").reason == "missing_blinded_quality_weight"
    assert (
        _metric(zero, "quality_weighted_diversity").reason == "zero_total_held_out_quality_weight"
    )


@pytest.mark.parametrize("weight", [-1.0, math.nan, math.inf, -math.inf])
def test_invalid_quality_weights_are_rejected_at_the_typed_boundary(weight: float) -> None:
    payload = quality_review(source_group(0)).model_dump(mode="python")
    payload["weight"] = weight

    with pytest.raises(ValidationError):
        operator_f.TrustedQualityReview.model_validate(payload)
