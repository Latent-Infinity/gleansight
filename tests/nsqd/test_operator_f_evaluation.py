from __future__ import annotations

import hashlib
import math

import pytest

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_support import (
    FOLD_SEED,
    METRIC_NAMES,
    balanced_inputs,
    inputs,
    source_group,
)


@pytest.mark.parametrize("eligible_count", range(5))
def test_zero_through_four_groups_return_replayable_typed_unavailable(
    eligible_count: int,
) -> None:
    result = operator_f.evaluate_operator_f(
        inputs(tuple(source_group(index) for index in range(eligible_count)))
    )

    assert isinstance(result, operator_f.OperatorFUnavailableResult)
    assert result.blocker == "insufficient_eligible_source_groups"
    assert result.eligible_source_group_identities == tuple(
        sorted(f"doi:10.0000/work-{index}" for index in range(eligible_count))
    )
    assert tuple(metric.name for metric in result.metrics) == METRIC_NAMES
    assert all(
        metric.state == "unavailable" and metric.reason == "insufficient_eligible_source_groups"
        for metric in result.metrics
    )
    assert result.authorization_state == "report_only"
    assert result.validation_target_scope == "evaluation_only"
    assert result.runtime_authorized is False
    assert result.schema_admission_authorized is False
    assert result.evidence_sufficient is False
    assert result.recommendation is None
    assert result.threshold_status == "human_decision_required_before_outcome_unblinding"
    assert result.thresholds == ()


def test_current_canonical_inventory_excludes_missingness_before_unavailability() -> None:
    records = (
        source_group(1, eligible=False).model_copy(
            update={"canonical_work_identity": "doi:10.2139/ssrn.6855118"}
        ),
        source_group(2).model_copy(update={"canonical_work_identity": "arxiv:2409.17392"}),
        source_group(3).model_copy(
            update={"canonical_work_identity": "doi:10.1016/j.eswa.2024.123538"}
        ),
        source_group(4).model_copy(update={"canonical_work_identity": "arxiv:2512.12727"}),
        source_group(5, eligible=False).model_copy(
            update={"canonical_work_identity": "doi:10.1145/3533271.3561687"}
        ),
    )

    result = operator_f.evaluate_operator_f(inputs(records, approvals=()))

    assert isinstance(result, operator_f.OperatorFUnavailableResult)
    assert result.eligible_source_group_identities == ()
    assert result.excluded_source_group_identities == (
        "arxiv:2409.17392",
        "arxiv:2512.12727",
        "doi:10.1016/j.eswa.2024.123538",
        "doi:10.1145/3533271.3561687",
        "doi:10.2139/ssrn.6855118",
    )
    assert result.fold_definition.assignments == ()
    assert result.authorization_state == "report_only"
    assert result.runtime_authorized is False
    assert result.schema_admission_authorized is False


def test_successor_fold_order_and_assignment_match_independent_sha256_oracle() -> None:
    result = operator_f.evaluate_operator_f(inputs(source_group(index) for index in range(5)))

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert result.fold_definition.algorithm == "sha256_seeded_source_group_round_robin/v1"
    assert result.fold_definition.seed == FOLD_SEED
    assert tuple(
        (item.canonical_work_identity, item.digest, item.fold_index)
        for item in result.fold_definition.assignments
    ) == (
        (
            "doi:10.0000/work-4",
            "115d0bbf738d7f3bd4a78ae155d58b5c797ef0eaa884cee7405000a200f59214",
            0,
        ),
        (
            "doi:10.0000/work-3",
            "3f52d329ac0341e39cfbd5d2720776acb0945bcc50a0de63ab62d21e2fdaf6eb",
            1,
        ),
        (
            "doi:10.0000/work-0",
            "6e7c4bf251f78f038acbf5a250d5a66bb13513a880709910c6fc72c7591036c7",
            2,
        ),
        (
            "doi:10.0000/work-1",
            "ed2ff3a7f1e995004a6b15e4be884d213e41269ee025c29cb7c8d38a79a9cedc",
            3,
        ),
        (
            "doi:10.0000/work-2",
            "faf10569ce9fe81a9646c5906faede8776f4792619965e7ade446c8d8f6b4ff7",
            4,
        ),
    )
    independent = tuple(
        sorted(
            (
                hashlib.sha256(f"{FOLD_SEED}:{item.canonical_work_identity}".encode()).hexdigest(),
                item.canonical_work_identity,
            )
            for item in inputs(source_group(index) for index in range(5)).source_groups
        )
    )
    assert (
        tuple(
            (item.digest, item.canonical_work_identity)
            for item in result.fold_definition.assignments
        )
        == independent
    )


def test_all_tracks_lock_identical_population_folds_and_versions() -> None:
    records = tuple(source_group(index) for index in range(5))
    records = (
        records[0].model_copy(
            update={"all_version_identities": ("work-0:v1", "work-0:v2", "work-0:v3")}
        ),
        *records[1:],
    )

    result = operator_f.evaluate_operator_f(inputs(records))

    assert isinstance(result, operator_f.OperatorFReportResult)
    populations = {track.eligible_source_group_identities for track in result.tracks}
    folds = {track.fold_assignments for track in result.tracks}
    assert len(populations) == len(folds) == 1
    work_zero = tuple(
        assignment
        for assignment in result.fold_definition.assignments
        if assignment.canonical_work_identity == "doi:10.0000/work-0"
    )
    assert len(work_zero) == 1


def test_exclusions_do_not_perturb_assignment_or_shuffle_population() -> None:
    eligible = tuple(source_group(index) for index in range(5))
    with_excluded = (*eligible, source_group(98, eligible=False), source_group(99, eligible=False))

    baseline = operator_f.evaluate_operator_f(inputs(eligible))
    expanded = operator_f.evaluate_operator_f(inputs(with_excluded))

    assert isinstance(baseline, operator_f.OperatorFReportResult)
    assert isinstance(expanded, operator_f.OperatorFReportResult)
    assert expanded.fold_definition == baseline.fold_definition
    assert expanded.shuffle == baseline.shuffle
    assert expanded.excluded_source_group_identities == (
        "doi:10.0000/work-98",
        "doi:10.0000/work-99",
    )


def test_shuffled_control_is_deterministic_fixed_point_free_and_outcome_independent() -> None:
    first_inputs = inputs(source_group(index) for index in range(7))
    altered = tuple(
        record.model_copy(update={"primary_metric": operator_f.PrimaryMetric(name="other")})
        for record in reversed(first_inputs.source_groups)
    )

    first = operator_f.evaluate_operator_f(first_inputs)
    second = operator_f.evaluate_operator_f(inputs(altered))

    assert isinstance(first, operator_f.OperatorFReportResult)
    assert isinstance(second, operator_f.OperatorFReportResult)
    assert first.shuffle == second.shuffle
    assert first.shuffle.fixed_point_free is True
    assert all(
        item.canonical_work_identity != item.receives_validation_target_from
        for item in first.shuffle.assignments
    )


def test_training_only_category_support_marks_redundancy_and_residual_unavailable() -> None:
    base = tuple(source_group(index, target="predictive_task") for index in range(10))
    order = sorted(
        base,
        key=lambda item: (
            hashlib.sha256(f"{FOLD_SEED}:{item.canonical_work_identity}".encode()).hexdigest(),
            item.canonical_work_identity,
        ),
    )
    unique = order[0].model_copy(update={"validation_target": "calibrated_risk"})
    records = tuple(unique if item is order[0] else item for item in base)

    result = operator_f.evaluate_operator_f(inputs(records))

    assert isinstance(result, operator_f.OperatorFReportResult)
    metrics = {metric.name: metric for metric in result.metrics}
    assert metrics["redundancy"].state == "unavailable"
    assert metrics["redundancy"].reason == "held_out_category_absent_from_training_groups"
    assert metrics["residual_variation"].state == "unavailable"
    assert (
        metrics["residual_variation"].reason
        == "required_category_support_absent_from_training_groups"
    )


def test_all_eight_metrics_replay_finite_candidate_fold_values_and_means() -> None:
    trusted_inputs = balanced_inputs()

    result = operator_f.evaluate_operator_f(trusted_inputs)
    replay = operator_f.evaluate_operator_f(trusted_inputs)

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert result == replay
    metrics = {metric.name: metric for metric in result.metrics}
    assert tuple(metrics) == METRIC_NAMES
    for metric in (item for name, item in metrics.items() if name != "quality_weighted_diversity"):
        candidate = next(
            series
            for series in metric.series
            if series.track_id == "current_axes_plus_validation_target"
        )
        assert candidate.state == "available"
        values = tuple(item.value for item in candidate.observations)
        assert all(value is not None and math.isfinite(value) for value in values)
        assert candidate.aggregate_value is not None
        assert math.isfinite(candidate.aggregate_value)
    for name in (
        "held_out_gain",
        "density",
        "stability",
        "redundancy",
        "residual_variation",
    ):
        candidate = next(
            series
            for series in metrics[name].series
            if series.track_id == "current_axes_plus_validation_target"
        )
        assert tuple(item.fold_index for item in candidate.observations) == (0, 1, 2, 3, 4)
        values = tuple(item.value for item in candidate.observations)
        assert all(value is not None for value in values)
        assert candidate.arithmetic_mean == pytest.approx(
            sum(value for value in values if value is not None) / 5
        )
    assert metrics["held_out_gain"].series[0].aggregate_value == pytest.approx(0.0)
    assert metrics["quality_weighted_diversity"].state == "available"
    assert metrics["quality_weighted_diversity"].series[1].aggregate_value == pytest.approx(0.5)
    assert metrics["stability"].series[0].aggregate_value == pytest.approx(1.0)
    assert metrics["redundancy"].series[0].aggregate_value == pytest.approx(1.0)
    assert metrics["residual_variation"].series[0].aggregate_value == pytest.approx(0.0)
    assert metrics["confound_sensitivity"].series[0].aggregate_value == pytest.approx(0.0)
    assert metrics["interpretability"].series[0].aggregate_value == pytest.approx(1.0)
