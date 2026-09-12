from __future__ import annotations

import pytest

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_remediation_support import (
    interpretability_reviews,
    quality_review,
    records_in_fold_order,
)
from tests.nsqd.operator_f_evaluation_support import inputs


def _metric(
    result: operator_f.OperatorFReportResult,
    name: operator_f.MetricName,
) -> operator_f.MetricResult:
    return next(metric for metric in result.metrics if metric.name == name)


def _candidate(metric: operator_f.MetricResult) -> operator_f.MetricSeries:
    return next(
        series
        for series in metric.series
        if series.track_id == "current_axes_plus_validation_target"
    )


def test_stability_uses_population_standard_deviation() -> None:
    ordered = records_in_fold_order(10)
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism=f"fold-{rank % 5}",
                    target="shared",
                    horizon="shared",
                ),
                "validation_target": ("economic_utility" if rank == 5 else "predictive_task"),
            }
        )
        for rank, record in enumerate(ordered)
    )

    result = operator_f.evaluate_operator_f(inputs(records))

    assert isinstance(result, operator_f.OperatorFReportResult)
    candidate = _candidate(_metric(result, "stability"))
    assert tuple(item.value for item in candidate.observations) == (1.0, 0.0, 0.0, 0.0, 0.0)
    assert candidate.aggregate_value == pytest.approx(2 / 3)


def test_training_redundancy_and_residual_variation_match_nontrivial_fixed_oracles() -> None:
    ordered = records_in_fold_order(40)
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism="a" if rank // 5 < 4 else "b",
                    target="a" if rank // 5 < 4 else "b",
                    horizon="a" if rank // 5 < 4 else "b",
                ),
                "validation_target": ("predictive_task" if rank // 5 < 5 else "economic_utility"),
            }
        )
        for rank, record in enumerate(ordered)
    )

    result = operator_f.evaluate_operator_f(inputs(records))

    assert isinstance(result, operator_f.OperatorFReportResult)
    redundancy = _candidate(_metric(result, "redundancy"))
    residual = _candidate(_metric(result, "residual_variation"))
    assert redundancy.aggregate_value == pytest.approx(0.7659416862050705)
    assert tuple(item.value for item in redundancy.observations) == pytest.approx(
        (0.7659416862050705,) * 5
    )
    assert residual.aggregate_value == pytest.approx(0.42500483112131604)
    assert tuple(item.value for item in residual.observations) == pytest.approx(
        (0.42500483112131604,) * 5
    )


def test_confound_sensitivity_matches_nonzero_stratum_oracle() -> None:
    ordered = records_in_fold_order(20)
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism="stratum-a" if rank // 5 < 2 else "stratum-b",
                    target="shared",
                    horizon="shared",
                ),
                "validation_target": ("economic_utility" if rank // 5 == 1 else "predictive_task"),
                "provenance": record.provenance.model_copy(
                    update={
                        "confound_strata": (
                            operator_f.ConfoundStratum(
                                name="venue",
                                value="a" if rank // 5 < 2 else "b",
                            ),
                        )
                    }
                ),
            }
        )
        for rank, record in enumerate(ordered)
    )

    result = operator_f.evaluate_operator_f(inputs(records))

    assert isinstance(result, operator_f.OperatorFReportResult)
    candidate = _candidate(_metric(result, "confound_sensitivity"))
    assert tuple(item.value for item in candidate.observations) == (0.0, 1.0)
    assert candidate.arithmetic_mean == pytest.approx(0.5)
    assert candidate.aggregate_value == pytest.approx(1.0)


def test_quality_and_interpretability_use_separate_trusted_oracles() -> None:
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism=f"unique-{index}",
                    target="shared",
                    horizon="shared",
                )
            }
        )
        for index, record in enumerate(records_in_fold_order(10))
    )
    quality = tuple(quality_review(record, 0.25 + index) for index, record in enumerate(records))
    reviews = interpretability_reviews(records, ratings=(0, 1))
    trusted = inputs(records, quality_reviews=quality, reviews=reviews)

    result = operator_f.evaluate_operator_f(trusted)

    assert isinstance(result, operator_f.OperatorFReportResult)
    quality_metric = _candidate(_metric(result, "quality_weighted_diversity"))
    interpretability = _metric(result, "interpretability")
    assert tuple(item.value for item in quality_metric.observations) == (1.0,) * 5
    assert interpretability.series[0].aggregate_value == pytest.approx(0.75)
    assert interpretability.disagreements == ("operational_definition",)
