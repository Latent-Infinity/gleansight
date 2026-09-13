from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from research.financial_jepa.contracts import (
    DevelopmentData,
    ExperimentConfig,
    RidgeData,
    Variant,
    YieldRow,
)
from research.financial_jepa.dataset import prepare_splits
from research.financial_jepa.evaluation import (
    diagnostics,
    fit_readouts,
    fit_ridge,
    metric_summary,
    select_ridge,
)
from research.financial_jepa.training import train_variant
from tests.research.support import curve, scale


def test_ridge_uses_declared_objective_and_unpenalized_intercept() -> None:
    features = np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64)
    targets = np.asarray([[1.0], [3.0], [5.0]], dtype=np.float64)

    ridge = fit_ridge(features, targets, alpha=0.0)

    assert np.allclose(ridge.coefficients, [[2.0]])
    assert np.allclose(ridge.intercept, [1.0])


def test_ridge_zeros_constant_learned_columns_without_rejecting_fit() -> None:
    features = np.asarray([[5.0, 0.0], [5.0, 1.0], [5.0, 2.0]], dtype=np.float64)
    targets = np.asarray([[1.0], [3.0], [5.0]], dtype=np.float64)

    ridge = fit_ridge(features, targets, alpha=0.0)

    assert ridge.feature_std[0] == 1.0
    assert np.allclose(ridge.coefficients, [[0.0], [2.0]])
    assert np.allclose(ridge.intercept, [1.0])


def test_ridge_all_constant_learned_features_predict_training_mean() -> None:
    features = np.full((3, 2), 5.0, dtype=np.float64)
    targets = np.asarray([[1.0], [3.0], [8.0]], dtype=np.float64)

    ridge = fit_ridge(features, targets, alpha=1.0)

    assert np.array_equal(ridge.coefficients, np.zeros((2, 1)))
    assert np.allclose(ridge.intercept, targets.mean(axis=0))


def test_alpha_selection_uses_validation_and_smallest_tie() -> None:
    train = RidgeData(
        features=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        targets=np.asarray([[1.0], [3.0], [5.0]], dtype=np.float64),
    )
    validation = RidgeData(
        features=np.asarray([[3.0], [4.0]], dtype=np.float64),
        targets=np.asarray([[7.0], [9.0]], dtype=np.float64),
    )

    selected = select_ridge(train, validation, (0.0, 0.0, 1.0))

    assert selected.alpha == 0.0


def test_metric_summary_reports_basis_points_all_axes() -> None:
    actual = np.zeros((2, 2, 3), dtype=np.float64)
    predicted = np.full((2, 2, 3), 0.01, dtype=np.float64)

    metrics = metric_summary(actual, predicted)

    assert metrics.overall_rmse_bp == 1.0
    assert metrics.per_horizon_rmse_bp == (1.0, 1.0)
    assert metrics.per_tenor_rmse_bp == (1.0, 1.0, 1.0)
    assert metrics.matrix_rmse_bp == ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))


def test_diagnostics_handles_zero_trace_and_detects_collapse() -> None:
    collapsed = diagnostics(np.ones((5, 16), dtype=np.float64))
    healthy = diagnostics(np.eye(16, dtype=np.float64) * 4.0)

    assert collapsed.effective_rank == 0.0
    assert collapsed.collapsed is True
    assert healthy.effective_rank >= 2.0


def test_diagnostics_retains_frequency_of_unique_observation_rows() -> None:
    retained_rows = np.concatenate(
        (np.zeros((100, 16), dtype=np.float64), np.eye(16, dtype=np.float64)),
        axis=0,
    )

    result = diagnostics(retained_rows)

    assert result.mean_sample_std == pytest.approx(0.0928476691)
    assert result.collapsed is True


def test_test_perturbation_cannot_change_train_scaler() -> None:
    config = ExperimentConfig.synthetic(context_length=2, future_length=1, batch_size=2, epochs=1)
    rows: list[YieldRow] = []
    for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0)):
        rows.extend(
            YieldRow(
                observed_on=date(year, 1, 1) + timedelta(days=index),
                yields=curve(base + index, 1.0),
                boundary_before=False,
            )
            for index in range(6)
        )
    first = prepare_splits(tuple(rows), config)
    perturbed = tuple(
        YieldRow(row.observed_on, curve(row.yields[0] + 1000, 1.0), row.boundary_before)
        if row.observed_on.year >= 2022
        else row
        for row in rows
    )
    second = prepare_splits(perturbed, config)

    assert np.array_equal(first.scaler.mean, second.scaler.mean)
    assert np.array_equal(first.scaler.std, second.scaler.std)


def test_test_perturbation_cannot_change_checkpoint_selection_or_readouts() -> None:
    config = ExperimentConfig.synthetic(context_length=2, future_length=1, batch_size=2, epochs=1)
    rows: list[YieldRow] = []
    for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0)):
        rows.extend(
            YieldRow(
                observed_on=date(year, 1, 1) + timedelta(days=index),
                yields=curve(base + index * 0.1, 0.2),
                boundary_before=False,
            )
            for index in range(22)
        )
    original = prepare_splits(tuple(rows), config)
    changed_rows = tuple(
        YieldRow(row.observed_on, scale(row.yields, 100.0), False)
        if row.observed_on.year == 2022
        else row
        for row in rows
    )
    changed = prepare_splits(changed_rows, config)
    first_trained = train_variant(
        DevelopmentData(original.train, original.validation), config, Variant.REGULARIZED, 17
    )
    second_trained = train_variant(
        DevelopmentData(changed.train, changed.validation), config, Variant.REGULARIZED, 17
    )
    first_readouts = fit_readouts(original.train, original.validation, first_trained, config)
    second_readouts = fit_readouts(changed.train, changed.validation, second_trained, config)

    assert first_trained.selected_epoch == second_trained.selected_epoch
    assert first_trained.state_sha256 == second_trained.state_sha256
    assert first_readouts.alpha == second_readouts.alpha
    assert all(
        np.array_equal(first.coefficients, second.coefficients)
        for first, second in zip(first_readouts.readouts, second_readouts.readouts, strict=True)
    )
