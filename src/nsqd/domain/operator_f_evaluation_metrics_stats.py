from __future__ import annotations

import math

from nsqd.domain.operator_f_evaluation_metrics_basic import (
    _available_series,
    _labels,
    _records_by_fold,
    metric_result,
    unavailable_series,
)
from nsqd.domain.operator_f_evaluation_trust_rules import (
    fold_definition_digest,
    source_population_digest,
)
from nsqd.domain.operator_f_evaluation_types import (
    FoldDefinition,
    MetricObservation,
    MetricResult,
    MetricSeries,
    MetricUnavailableReason,
    OperatorFSourceGroup,
    TrackReplay,
    TrustedInterpretabilityReview,
    ValidationTarget,
)


def _axis_values(record: OperatorFSourceGroup) -> tuple[str, str, str]:
    coordinates = record.registered_coordinates
    assert coordinates is not None
    return coordinates.mechanism, coordinates.target, coordinates.horizon


def _cramers_v(pairs: tuple[tuple[str, ValidationTarget], ...]) -> float | None:
    axis_categories = tuple(sorted({axis for axis, _ in pairs}))
    target_categories = tuple(sorted({target for _, target in pairs}))
    sample_count = len(pairs)
    if sample_count < 2 or len(axis_categories) < 2 or len(target_categories) < 2:
        return None
    row_totals = {axis: sum(item[0] == axis for item in pairs) for axis in axis_categories}
    column_totals = {
        target: sum(item[1] == target for item in pairs) for target in target_categories
    }
    chi_squared = 0.0
    for axis in axis_categories:
        for target in target_categories:
            observed = sum(item == (axis, target) for item in pairs)
            expected = row_totals[axis] * column_totals[target] / sample_count
            chi_squared += (observed - expected) ** 2 / expected
    phi_squared = chi_squared / sample_count
    correction = (len(target_categories) - 1) * (len(axis_categories) - 1) / (sample_count - 1)
    corrected_phi = max(0.0, phi_squared - correction)
    corrected_rows = len(axis_categories) - (len(axis_categories) - 1) ** 2 / (sample_count - 1)
    corrected_columns = len(target_categories) - (len(target_categories) - 1) ** 2 / (
        sample_count - 1
    )
    denominator = min(corrected_rows - 1, corrected_columns - 1)
    return None if denominator <= 0 else float(math.sqrt(corrected_phi / denominator))


def redundancy(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> MetricResult:
    series: list[MetricSeries] = []
    for track in tracks[1:]:
        labels = _labels(track)
        fold_values: list[float] = []
        unavailable_reason: MetricUnavailableReason | None = None
        folds = _records_by_fold(records, track)
        for fold_index, held_out in enumerate(folds):
            training = tuple(
                record for index, fold in enumerate(folds) if index != fold_index for record in fold
            )
            training_targets = {labels[record.canonical_work_identity] for record in training}
            held_targets = {labels[record.canonical_work_identity] for record in held_out}
            training_axes = tuple(
                {values[axis_index] for record in training for values in (_axis_values(record),)}
                for axis_index in range(3)
            )
            held_axes = tuple(
                {values[axis_index] for record in held_out for values in (_axis_values(record),)}
                for axis_index in range(3)
            )
            if not held_targets.issubset(training_targets) or any(
                not held.issubset(trained)
                for held, trained in zip(held_axes, training_axes, strict=True)
            ):
                unavailable_reason = "held_out_category_absent_from_training_groups"
                break
            associations = tuple(
                _cramers_v(
                    tuple(
                        (
                            _axis_values(record)[axis_index],
                            labels[record.canonical_work_identity],
                        )
                        for record in training
                    )
                )
                for axis_index in range(3)
            )
            if any(value is None for value in associations):
                unavailable_reason = "degenerate_contingency_table"
                break
            fold_values.append(float(max(value for value in associations if value is not None)))
        series.append(
            unavailable_series(track.track_id, unavailable_reason)
            if unavailable_reason is not None
            else _available_series(track.track_id, tuple(fold_values))
        )
    return metric_result("redundancy", tuple(series))


def _entropy(values: tuple[str, ...]) -> float:
    frequencies = tuple(values.count(value) / len(values) for value in set(values))
    return float(-sum(probability * math.log2(probability) for probability in frequencies))


def _conditional_entropy(
    coordinates: tuple[tuple[str, str, str], ...],
    labels: tuple[str, ...],
) -> float:
    total = len(labels)
    value = 0.0
    for coordinate in set(coordinates):
        selected = tuple(
            label for item, label in zip(coordinates, labels, strict=True) if item == coordinate
        )
        value += len(selected) / total * _entropy(selected)
    return float(value)


def residual_variation(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> MetricResult:
    series: list[MetricSeries] = []
    for track in tracks[1:]:
        labels = _labels(track)
        fold_values: list[float] = []
        unavailable_reason: MetricUnavailableReason | None = None
        folds = _records_by_fold(records, track)
        for fold_index, held_out in enumerate(folds):
            training = tuple(
                record for index, fold in enumerate(folds) if index != fold_index for record in fold
            )
            training_targets = {labels[record.canonical_work_identity] for record in training}
            training_coordinates = {_axis_values(record) for record in training}
            held_targets = tuple(labels[record.canonical_work_identity] for record in held_out)
            held_coordinates = tuple(_axis_values(record) for record in held_out)
            if not set(held_targets).issubset(training_targets) or not set(
                held_coordinates
            ).issubset(training_coordinates):
                unavailable_reason = "required_category_support_absent_from_training_groups"
                break
            entropy = _entropy(held_targets)
            if entropy == 0.0:
                unavailable_reason = "zero_held_out_validation_target_entropy"
                break
            fold_values.append(_conditional_entropy(held_coordinates, held_targets) / entropy)
        series.append(
            unavailable_series(track.track_id, unavailable_reason)
            if unavailable_reason is not None
            else _available_series(track.track_id, tuple(fold_values))
        )
    return metric_result("residual_variation", tuple(series))


def interpretability(
    records: tuple[OperatorFSourceGroup, ...],
    folds: FoldDefinition,
    reviews: tuple[TrustedInterpretabilityReview, ...],
) -> MetricResult:
    identities = tuple(review.reviewer_identity for review in reviews)
    sessions = tuple(review.reviewer_session for review in reviews)
    item_sets = tuple(tuple(item.name for item in review.ratings) for review in reviews)
    predeclared_items = tuple(review.predeclared_rating_items for review in reviews)
    producer_identities = {record.provenance.producer_identity for record in records}
    producer_sessions = {record.provenance.producer_session for record in records}
    expected_population = source_population_digest(records)
    expected_folds = fold_definition_digest(folds)
    complete = (
        len(reviews) >= 2
        and len(identities) == len(set(identities))
        and len(sessions) == len(set(sessions))
        and all(identity.startswith("human:") for identity in identities)
        and producer_identities.isdisjoint(identities)
        and producer_sessions.isdisjoint(sessions)
        and all(items and items == item_sets[0] for items in item_sets)
        and all(items == predeclared_items[0] for items in predeclared_items)
        and all(review.source_population_digest == expected_population for review in reviews)
        and all(review.fold_assignment_digest == expected_folds for review in reviews)
    )
    if not complete:
        series = unavailable_series(
            "current_axes_plus_validation_target",
            "missing_independent_blinded_interpretability_rating",
        )
        return metric_result("interpretability", (series,))
    observations = tuple(
        MetricObservation(
            label=f"{review.reviewer_identity}:{item.name}",
            fold_index=None,
            state="available",
            value=float(item.rating),
            reason=None,
        )
        for review in reviews
        for item in review.ratings
    )
    values = tuple(item.value for item in observations if item.value is not None)
    mean = float(sum(values) / len(values))
    by_item = {
        name: tuple(
            item.rating for review in reviews for item in review.ratings if item.name == name
        )
        for name in item_sets[0]
    }
    disagreements = tuple(
        sorted(name for name, ratings in by_item.items() if len(set(ratings)) > 1)
    )
    series = MetricSeries(
        track_id="current_axes_plus_validation_target",
        state="available",
        observations=observations,
        arithmetic_mean=mean,
        aggregate_value=mean,
        reason=None,
    )
    return MetricResult(
        name="interpretability",
        state="available",
        series=(series,),
        reason=None,
        disagreements=disagreements,
    )
