from __future__ import annotations

import hashlib

from nsqd.domain import operator_f_evaluation as operator_f
from nsqd.domain.operator_f_evaluation_metrics_stats import redundancy
from nsqd.domain.operator_f_evaluation_types import (
    FoldAssignment,
    TrackLabel,
    TrackReplay,
    ValidationTarget,
)
from tests.nsqd.operator_f_evaluation_support import source_group


def _records() -> tuple[operator_f.OperatorFSourceGroup, ...]:
    return tuple(
        source_group(index).model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism="a" if index // 5 < 2 else "b",
                    target="a" if index // 5 < 2 else "b",
                    horizon="a" if index // 5 < 2 else "b",
                )
            }
        )
        for index in range(20)
    )


def _perfect_labels(
    records: tuple[operator_f.OperatorFSourceGroup, ...],
) -> dict[str, ValidationTarget]:
    return {
        record.canonical_work_identity: (
            "predictive_task" if index // 5 < 2 else "economic_utility"
        )
        for index, record in enumerate(records)
    }


def _independent_labels(
    records: tuple[operator_f.OperatorFSourceGroup, ...],
) -> dict[str, ValidationTarget]:
    return {
        record.canonical_work_identity: (
            "predictive_task" if index // 5 in {0, 2} else "economic_utility"
        )
        for index, record in enumerate(records)
    }


def _tracks(
    records: tuple[operator_f.OperatorFSourceGroup, ...],
    candidate: dict[str, ValidationTarget],
    shuffled: dict[str, ValidationTarget] | None = None,
) -> tuple[TrackReplay, TrackReplay, TrackReplay]:
    identities = tuple(record.canonical_work_identity for record in records)
    assignments = tuple(
        FoldAssignment(
            canonical_work_identity=identity,
            digest=hashlib.sha256(identity.encode()).hexdigest(),
            fold_index=index % 5,
        )
        for index, identity in enumerate(identities)
    )
    shuffled_labels = candidate if shuffled is None else shuffled

    def track(track_id: str, labels: dict[str, ValidationTarget]) -> TrackReplay:
        return TrackReplay(
            track_id=track_id,
            eligible_source_group_identities=identities,
            fold_assignments=assignments,
            labels=tuple(
                TrackLabel(canonical_work_identity=identity, validation_target=labels[identity])
                for identity in identities
            ),
        )

    return (
        TrackReplay(
            track_id="current_registered_axes",
            eligible_source_group_identities=identities,
            fold_assignments=assignments,
            labels=(),
        ),
        track("current_axes_plus_validation_target", candidate),
        track("current_axes_plus_shuffled_validation_target", shuffled_labels),
    )


def test_redundancy_uses_training_association_with_held_out_fold_fixed() -> None:
    records = _records()
    perfect = _perfect_labels(records)
    independent_training = dict(perfect)
    independent = _independent_labels(records)
    for index, record in enumerate(records):
        if index % 5 != 0:
            independent_training[record.canonical_work_identity] = independent[
                record.canonical_work_identity
            ]

    perfect_result = redundancy(records, _tracks(records, perfect))
    independent_result = redundancy(records, _tracks(records, independent_training))

    assert perfect_result.series[0].observations[0].value == 1.0
    assert independent_result.series[0].observations[0].value == 0.0


def test_redundancy_does_not_refit_on_held_out_frequencies() -> None:
    records = _records()
    perfect = _perfect_labels(records)
    changed_held_out = dict(perfect)
    independent = _independent_labels(records)
    for index, record in enumerate(records):
        if index % 5 == 0:
            changed_held_out[record.canonical_work_identity] = independent[
                record.canonical_work_identity
            ]

    first = redundancy(records, _tracks(records, perfect))
    second = redundancy(records, _tracks(records, changed_held_out))

    assert first.series[0].observations[0].value == 1.0
    assert second.series[0].observations[0].value == 1.0


def test_redundancy_averages_five_training_fits_and_keeps_track_labels_separate() -> None:
    records = _records()
    result = redundancy(
        records,
        _tracks(records, _perfect_labels(records), _independent_labels(records)),
    )

    candidate, shuffled = result.series
    assert tuple(observation.value for observation in candidate.observations) == (1.0,) * 5
    assert candidate.arithmetic_mean == 1.0
    assert candidate.aggregate_value == 1.0
    assert tuple(observation.value for observation in shuffled.observations) == (0.0,) * 5
    assert shuffled.arithmetic_mean == 0.0
    assert shuffled.aggregate_value == 0.0


def test_redundancy_takes_the_maximum_training_fit_across_registered_axes() -> None:
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism="a" if index // 5 in {0, 2} else "b",
                    target="a" if index // 5 < 2 else "b",
                    horizon="a" if index // 5 in {0, 2} else "b",
                )
            }
        )
        for index, record in enumerate(_records())
    )

    result = redundancy(records, _tracks(records, _perfect_labels(records)))

    assert tuple(observation.value for observation in result.series[0].observations) == (1.0,) * 5


def test_redundancy_requires_held_out_category_support_in_training() -> None:
    records = _records()
    labels = _perfect_labels(records)
    labels[records[0].canonical_work_identity] = "calibrated_risk"

    result = redundancy(records, _tracks(records, labels))

    assert result.state == "unavailable"
    assert result.reason == "held_out_category_absent_from_training_groups"
    assert result.series[0].state == "unavailable"
    assert result.series[0].observations == ()


def test_redundancy_requires_held_out_axis_support_in_training() -> None:
    base = _records()
    first = base[0]
    coordinates = first.registered_coordinates
    assert coordinates is not None
    unsupported = first.model_copy(
        update={
            "registered_coordinates": coordinates.model_copy(update={"mechanism": "held-out-only"})
        }
    )
    records = (unsupported, *base[1:])

    result = redundancy(records, _tracks(records, _perfect_labels(records)))

    assert result.state == "unavailable"
    assert result.reason == "held_out_category_absent_from_training_groups"
    assert result.series[0].state == "unavailable"
    assert result.series[0].observations == ()


def test_redundancy_keeps_degenerate_training_tables_typed_unavailable() -> None:
    records = tuple(
        record.model_copy(
            update={
                "registered_coordinates": operator_f.RegisteredCoordinates(
                    mechanism="same",
                    target="same",
                    horizon="same",
                )
            }
        )
        for record in _records()
    )

    result = redundancy(records, _tracks(records, _independent_labels(records)))

    assert result.state == "unavailable"
    assert result.reason == "degenerate_contingency_table"
    assert result.series[0].state == "unavailable"
    assert result.series[0].observations == ()
