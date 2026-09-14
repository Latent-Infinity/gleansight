from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from research.financial_jepa.contracts import JsonValue, MetricSummary
from research.financial_jepa.diagnostic_probes import (
    MethodFit,
    SeedDiagnostics,
    representation_summary,
)


def _statistics(values: object) -> dict[str, JsonValue]:
    numeric = np.asarray(values, dtype=np.float64)
    return {
        "mean": numeric.mean(axis=0).tolist(),
        "population_std": numeric.std(axis=0, ddof=0).tolist(),
    }


def _metric_aggregate(metrics: Sequence[MetricSummary]) -> dict[str, JsonValue]:
    return {
        "overall_rmse_bp": _statistics([value.overall_rmse_bp for value in metrics]),
        "per_horizon_rmse_bp": _statistics([value.per_horizon_rmse_bp for value in metrics]),
        "per_tenor_rmse_bp": _statistics([value.per_tenor_rmse_bp for value in metrics]),
        "matrix_rmse_bp": _statistics([value.matrix_rmse_bp for value in metrics]),
    }


def _method_aggregate(methods: Sequence[MethodFit]) -> dict[str, JsonValue]:
    return _metric_aggregate([method.metrics for method in methods])


def _representation_aggregate(values: Sequence[np.ndarray]) -> dict[str, JsonValue]:
    summaries = [representation_summary(value) for value in values]
    return {
        "per_dimension_sample_std": _statistics([item[0] for item in summaries]),
        "mean_sample_std": _statistics([item[1].mean_sample_std for item in summaries]),
        "covariance_effective_rank": _statistics([item[1].effective_rank for item in summaries]),
    }


def seed_aggregates(seeds: Sequence[SeedDiagnostics]) -> dict[str, JsonValue]:
    latent_errors = [
        (seed.predicted_validation_latents - seed.selected_validation_future_latents) ** 2
        for seed in seeds
    ]
    persistence_errors = [
        (seed.selected_validation_current_latents - seed.selected_validation_future_latents) ** 2
        for seed in seeds
    ]
    return {
        "forecast_methods": {
            "selected_ema_current": _method_aggregate([seed.selected_current for seed in seeds]),
            "predicted_future": _method_aggregate([seed.predicted_future for seed in seeds]),
            "frozen_random_current": _method_aggregate(
                [seed.frozen_random_current for seed in seeds]
            ),
        },
        "latent": {
            "predicted_future": {
                "overall_mse": _statistics([value.mean() for value in latent_errors]),
                "per_horizon_mse": _statistics(
                    [value.mean(axis=(0, 2)) for value in latent_errors]
                ),
            },
            "ema_current_persistence": {
                "overall_mse": _statistics([value.mean() for value in persistence_errors]),
                "per_horizon_mse": _statistics(
                    [value.mean(axis=(0, 2)) for value in persistence_errors]
                ),
            },
        },
        "current_reconstruction": _method_aggregate([seed.reconstruction for seed in seeds]),
        "representations": {
            "train_selected_ema": _representation_aggregate(
                [seed.selected_train_embeddings for seed in seeds]
            ),
            "validation_selected_ema": _representation_aggregate(
                [seed.selected_validation_embeddings for seed in seeds]
            ),
            "train_frozen_random": _representation_aggregate(
                [seed.random_train_embeddings for seed in seeds]
            ),
            "validation_frozen_random": _representation_aggregate(
                [seed.random_validation_embeddings for seed in seeds]
            ),
        },
    }


def _record(value: JsonValue, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _record_axes(
    records: Sequence[Mapping[str, JsonValue]], axes: Sequence[str]
) -> dict[str, JsonValue]:
    return {axis: _statistics([record[axis] for record in records]) for axis in axes}


def verified_seed_aggregates(
    seeds: Sequence[Mapping[str, JsonValue]],
) -> dict[str, JsonValue]:
    metric_axes = (
        "overall_rmse_bp",
        "per_horizon_rmse_bp",
        "per_tenor_rmse_bp",
        "matrix_rmse_bp",
    )
    forecast: dict[str, JsonValue] = {}
    for method in ("selected_ema_current", "predicted_future", "frozen_random_current"):
        records = [_record(_record(seed["methods"], "methods")[method], method) for seed in seeds]
        forecast[method] = _record_axes(records, metric_axes)
    latent_records = [_record(seed["latent"], "latent") for seed in seeds]
    latent: dict[str, JsonValue] = {}
    for name, overall, per_horizon in (
        (
            "predicted_future",
            "predicted_future_overall_mse",
            "predicted_future_per_horizon_mse",
        ),
        (
            "ema_current_persistence",
            "ema_current_persistence_overall_mse",
            "ema_current_persistence_per_horizon_mse",
        ),
    ):
        latent[name] = {
            "overall_mse": _statistics([record[overall] for record in latent_records]),
            "per_horizon_mse": _statistics([record[per_horizon] for record in latent_records]),
        }
    representations: dict[str, JsonValue] = {}
    for name in (
        "train_selected_ema",
        "validation_selected_ema",
        "train_frozen_random",
        "validation_frozen_random",
    ):
        records = [
            _record(_record(seed["representations"], "representations")[name], name)
            for seed in seeds
        ]
        representations[name] = _record_axes(
            records,
            (
                "per_dimension_sample_std",
                "mean_sample_std",
                "covariance_effective_rank",
            ),
        )
    reconstruction = [
        _record(seed["current_reconstruction"], "current reconstruction") for seed in seeds
    ]
    return {
        "forecast_methods": forecast,
        "latent": latent,
        "current_reconstruction": _record_axes(reconstruction, metric_axes),
        "representations": representations,
    }
