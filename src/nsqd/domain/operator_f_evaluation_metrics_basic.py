from __future__ import annotations

import math
from collections.abc import Mapping

from nsqd.domain.operator_f_evaluation_types import (
    MetricName,
    MetricObservation,
    MetricResult,
    MetricSeries,
    MetricUnavailableReason,
    OperatorFSourceGroup,
    TrackId,
    TrackReplay,
    ValidationTarget,
)


def _records_by_fold(
    records: tuple[OperatorFSourceGroup, ...],
    track: TrackReplay,
) -> tuple[tuple[OperatorFSourceGroup, ...], ...]:
    by_identity = {record.canonical_work_identity: record for record in records}
    return tuple(
        tuple(
            by_identity[item.canonical_work_identity]
            for item in track.fold_assignments
            if item.fold_index == fold_index and item.canonical_work_identity in by_identity
        )
        for fold_index in range(5)
    )


def _labels(track: TrackReplay) -> dict[str, ValidationTarget]:
    return {item.canonical_work_identity: item.validation_target for item in track.labels}


type CellIdentity = tuple[str, str, str] | tuple[str, str, str, ValidationTarget]


def _cell(record: OperatorFSourceGroup, label: ValidationTarget | None) -> CellIdentity:
    coordinates = record.registered_coordinates
    assert coordinates is not None
    base = coordinates.mechanism, coordinates.target, coordinates.horizon
    return base if label is None else (*base, label)


def _fold_gains(
    records: tuple[OperatorFSourceGroup, ...],
    track: TrackReplay,
) -> tuple[float, ...]:
    labels = _labels(track)
    gains: list[float] = []
    for held_out in _records_by_fold(records, track):
        current = {_cell(record, None) for record in held_out}
        candidate = {_cell(record, labels[record.canonical_work_identity]) for record in held_out}
        gains.append(float(len(candidate) - len(current)))
    return tuple(gains)


def _available_series(
    track_id: TrackId,
    values: tuple[float, ...],
    aggregate: float | None = None,
) -> MetricSeries:
    mean = sum(values) / len(values)
    observations = tuple(
        MetricObservation(
            label=f"fold_{fold_index}",
            fold_index=fold_index,
            state="available",
            value=value,
            reason=None,
        )
        for fold_index, value in enumerate(values)
    )
    return MetricSeries(
        track_id=track_id,
        state="available",
        observations=observations,
        arithmetic_mean=float(mean),
        aggregate_value=float(mean if aggregate is None else aggregate),
        reason=None,
    )


def unavailable_series(
    track_id: TrackId,
    reason: MetricUnavailableReason,
) -> MetricSeries:
    return MetricSeries(
        track_id=track_id,
        state="unavailable",
        observations=(),
        arithmetic_mean=None,
        aggregate_value=None,
        reason=reason,
    )


def metric_result(name: MetricName, series: tuple[MetricSeries, ...]) -> MetricResult:
    unavailable: MetricUnavailableReason | None = None
    for item in series:
        if item.state == "unavailable":
            unavailable = item.reason
            break
    return MetricResult(
        name=name,
        state="unavailable" if unavailable is not None else "available",
        series=series,
        reason=unavailable,
    )


def held_out_gain(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> MetricResult:
    return metric_result(
        "held_out_gain",
        tuple(
            _available_series(track.track_id, _fold_gains(records, track)) for track in tracks[1:]
        ),
    )


def density(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> MetricResult:
    series: list[MetricSeries] = []
    for track in tracks:
        labels = _labels(track)
        values: list[float] = []
        for held_out in _records_by_fold(records, track):
            cells = {
                _cell(record, labels.get(record.canonical_work_identity)) for record in held_out
            }
            values.append(float(len(held_out) / len(cells)))
        series.append(_available_series(track.track_id, tuple(values)))
    return metric_result("density", tuple(series))


def quality_weighted_diversity(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
    trusted_weights: Mapping[str, float],
) -> MetricResult:
    series: list[MetricSeries] = []
    for track in tracks:
        labels = _labels(track)
        values: list[float] = []
        reason: MetricUnavailableReason | None = None
        for held_out in _records_by_fold(records, track):
            if any(record.canonical_work_identity not in trusted_weights for record in held_out):
                reason = "missing_blinded_quality_weight"
                break
            held_weights = tuple(
                trusted_weights[record.canonical_work_identity] for record in held_out
            )
            scale = max(held_weights, default=0.0)
            if scale == 0.0:
                reason = "zero_total_held_out_quality_weight"
                break
            cell_weights: dict[CellIdentity, float] = {}
            for record in held_out:
                cell = _cell(record, labels.get(record.canonical_work_identity))
                weight = trusted_weights[record.canonical_work_identity]
                cell_weights[cell] = max(weight, cell_weights.get(cell, 0.0))
            numerator = math.fsum(weight / scale for weight in cell_weights.values())
            denominator = math.fsum(weight / scale for weight in held_weights)
            values.append(float(numerator / denominator))
        series.append(
            unavailable_series(track.track_id, reason)
            if reason is not None
            else _available_series(track.track_id, tuple(values))
        )
    return metric_result("quality_weighted_diversity", tuple(series))


def stability(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> MetricResult:
    series: list[MetricSeries] = []
    for track in tracks[1:]:
        gains = _fold_gains(records, track)
        mean = sum(gains) / len(gains)
        deviation = math.sqrt(sum((value - mean) ** 2 for value in gains) / len(gains))
        value = 1.0 - deviation / (1.0 + abs(mean))
        series.append(_available_series(track.track_id, gains, float(value)))
    return metric_result("stability", tuple(series))


def confound_sensitivity(
    records: tuple[OperatorFSourceGroup, ...],
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> MetricResult:
    strata = tuple(
        sorted(
            {
                (stratum.name, stratum.value)
                for record in records
                for stratum in record.provenance.confound_strata
            }
        )
    )
    if not strata:
        series = tuple(
            unavailable_series(track.track_id, "no_predeclared_confound_strata")
            for track in tracks[1:]
        )
        return metric_result("confound_sensitivity", series)
    result_series: list[MetricSeries] = []
    for track in tracks[1:]:
        aggregate = sum(_fold_gains(records, track)) / 5
        differences: list[float] = []
        observations: list[MetricObservation] = []
        missing = False
        for name, value in strata:
            subset = tuple(
                record
                for record in records
                if any(
                    item.name == name and item.value == value
                    for item in record.provenance.confound_strata
                )
            )
            if any(not fold for fold in _records_by_fold(subset, track)):
                missing = True
                break
            stratum_gain = sum(_fold_gains(subset, track)) / 5
            difference = float(abs(aggregate - stratum_gain))
            differences.append(difference)
            observations.append(
                MetricObservation(
                    label=f"stratum:{name}={value}",
                    fold_index=None,
                    state="available",
                    value=difference,
                    reason=None,
                )
            )
        if missing:
            result_series.append(
                unavailable_series(
                    track.track_id,
                    "declared_stratum_missing_eligible_held_out_observation",
                )
            )
        else:
            result_series.append(
                MetricSeries(
                    track_id=track.track_id,
                    state="available",
                    observations=tuple(observations),
                    arithmetic_mean=float(sum(differences) / len(differences)),
                    aggregate_value=max(differences),
                    reason=None,
                )
            )
    return metric_result("confound_sensitivity", tuple(result_series))
