from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Final

import numpy as np
from pydantic import TypeAdapter

from research.financial_jepa.contracts import JsonValue, RidgeModel
from research.financial_jepa.diagnostic_artifacts import NumericArray
from research.financial_jepa.diagnostic_contracts import EpochRecord, RecordedTrainResult
from research.financial_jepa.diagnostic_probes import (
    MethodFit,
    SeedDiagnostics,
    representation_summary,
)
from research.financial_jepa.reporting import metric_record
from research.financial_jepa.training import state_digest

_JSON_RECORD_ADAPTER: Final = TypeAdapter(dict[str, JsonValue])


def state_arrays(recorded: tuple[RecordedTrainResult, ...]) -> dict[str, NumericArray]:
    arrays: dict[str, NumericArray] = {}
    for item in recorded:
        for label, state in (
            ("initial", item.initial_model_state),
            ("selected", item.result.model_state),
        ):
            for name, tensor in sorted(state.items()):
                arrays[f"seed_{item.result.seed}.{label}.{name}"] = (
                    tensor.detach().cpu().numpy().copy()
                )
    return arrays


def _ridge_arrays(prefix: str, models: tuple[RidgeModel, ...]) -> dict[str, NumericArray]:
    arrays: dict[str, NumericArray] = {}
    for index, model in enumerate(models):
        model_prefix = f"{prefix}.model_{index}"
        arrays[f"{model_prefix}.feature_mean"] = model.feature_mean
        arrays[f"{model_prefix}.feature_std"] = model.feature_std
        arrays[f"{model_prefix}.coefficients"] = model.coefficients
        arrays[f"{model_prefix}.intercept"] = model.intercept
    return arrays


def ridge_arrays(
    raw: MethodFit,
    seeds: tuple[SeedDiagnostics, ...],
    scaler_mean: np.ndarray,
    scaler_std: np.ndarray,
) -> dict[str, NumericArray]:
    arrays: dict[str, NumericArray] = {
        "dataset_scaler.mean": scaler_mean,
        "dataset_scaler.std": scaler_std,
    }
    arrays.update(_ridge_arrays("raw_history", raw.models))
    for seed in seeds:
        for name, method in (
            ("selected_ema_current", seed.selected_current),
            ("predicted_future", seed.predicted_future),
            ("frozen_random_current", seed.frozen_random_current),
            ("current_reconstruction", seed.reconstruction),
        ):
            arrays.update(_ridge_arrays(f"seed_{seed.seed}.{name}", method.models))
    return arrays


def validation_arrays(
    prepared_context: np.ndarray,
    prepared_raw_context: np.ndarray,
    actual: np.ndarray,
    origin_dates: np.ndarray,
    target_dates: np.ndarray,
    raw: MethodFit,
    persistence: np.ndarray,
    seeds: tuple[SeedDiagnostics, ...],
    validation_raw_rows: np.ndarray,
    validation_scaled_rows: np.ndarray,
    train_raw_rows: np.ndarray,
    train_row_dates: np.ndarray,
    validation_row_dates: np.ndarray,
) -> dict[str, NumericArray]:
    arrays: dict[str, NumericArray] = {
        "scaled_contexts": prepared_context,
        "raw_contexts": prepared_raw_context,
        "raw_actual_future": actual,
        "origin_dates": origin_dates,
        "target_dates": target_dates,
        "validation_raw_rows": validation_raw_rows,
        "validation_scaled_rows": validation_scaled_rows,
        "train_raw_rows": train_raw_rows,
        "train_row_dates": train_row_dates,
        "validation_row_dates": validation_row_dates,
        "forecast.persistence": persistence,
        "forecast.raw_history": raw.validation_prediction,
    }
    for seed in seeds:
        prefix = f"seed_{seed.seed}"
        arrays[f"forecast.{prefix}.selected_ema_current"] = (
            seed.selected_current.validation_prediction
        )
        arrays[f"forecast.{prefix}.predicted_future"] = seed.predicted_future.validation_prediction
        arrays[f"forecast.{prefix}.frozen_random_current"] = (
            seed.frozen_random_current.validation_prediction
        )
        arrays[f"latent.{prefix}.predicted_future"] = seed.predicted_validation_latents
        arrays[f"latent.{prefix}.ema_future"] = seed.selected_validation_future_latents
        arrays[f"latent.{prefix}.ema_current"] = seed.selected_validation_current_latents
        arrays[f"representation.{prefix}.train_selected"] = seed.selected_train_embeddings
        arrays[f"representation.{prefix}.validation_selected"] = seed.selected_validation_embeddings
        arrays[f"representation.{prefix}.train_random"] = seed.random_train_embeddings
        arrays[f"representation.{prefix}.validation_random"] = seed.random_validation_embeddings
        arrays[f"reconstruction.{prefix}.selected_ema"] = seed.reconstruction.validation_prediction[
            :, 0, :
        ]
    return arrays


def _method_record(method: MethodFit) -> dict[str, JsonValue]:
    record = metric_record(method.metrics)
    record["shared_alpha"] = method.alpha
    return record


def _epoch_record(epoch: EpochRecord) -> dict[str, JsonValue]:
    return {
        "epoch": epoch.epoch,
        "batch_count": epoch.batch_count,
        "window_count": epoch.window_count,
        "mean_prediction_loss": epoch.mean_prediction_loss,
        "mean_variance_loss": epoch.mean_variance_loss,
        "mean_covariance_loss": epoch.mean_covariance_loss,
        "mean_total_loss": epoch.mean_total_loss,
        "aligned_validation_mse": epoch.aligned_validation_mse,
        "checkpoint_updated": epoch.checkpoint_updated,
    }


def _representation_record(values: np.ndarray) -> dict[str, JsonValue]:
    per_dimension, summary = representation_summary(values)
    return _JSON_RECORD_ADAPTER.validate_python(
        {
            "per_dimension_sample_std": list(per_dimension),
            "mean_sample_std": summary.mean_sample_std,
            "covariance_effective_rank": summary.effective_rank,
        }
    )


def seed_record(
    recorded: RecordedTrainResult, diagnostics: SeedDiagnostics
) -> dict[str, JsonValue]:
    latent_error = (
        diagnostics.predicted_validation_latents - diagnostics.selected_validation_future_latents
    ) ** 2
    persistence_error = (
        diagnostics.selected_validation_current_latents
        - diagnostics.selected_validation_future_latents
    ) ** 2
    epochs: list[JsonValue] = [_epoch_record(epoch) for epoch in recorded.epochs]
    return {
        "seed": recorded.result.seed,
        "selected_epoch": recorded.result.selected_epoch,
        "aligned_validation_mse": recorded.result.validation_mse,
        "selected_state_sha256": recorded.result.state_sha256,
        "initial_state_sha256": state_digest(recorded.initial_model_state),
        "epochs": epochs,
        "methods": {
            "selected_ema_current": _method_record(diagnostics.selected_current),
            "predicted_future": _method_record(diagnostics.predicted_future),
            "frozen_random_current": _method_record(diagnostics.frozen_random_current),
        },
        "latent": {
            "predicted_future_overall_mse": float(latent_error.mean()),
            "predicted_future_per_horizon_mse": [
                float(value) for value in latent_error.mean(axis=(0, 2))
            ],
            "ema_current_persistence_overall_mse": float(persistence_error.mean()),
            "ema_current_persistence_per_horizon_mse": [
                float(value) for value in persistence_error.mean(axis=(0, 2))
            ],
        },
        "current_reconstruction": _method_record(diagnostics.reconstruction),
        "representations": {
            "train_selected_ema": _representation_record(diagnostics.selected_train_embeddings),
            "validation_selected_ema": _representation_record(
                diagnostics.selected_validation_embeddings
            ),
            "train_frozen_random": _representation_record(diagnostics.random_train_embeddings),
            "validation_frozen_random": _representation_record(
                diagnostics.random_validation_embeddings
            ),
        },
    }


def date_sha256(origin_dates: np.ndarray, target_dates: np.ndarray) -> str:
    digest = hashlib.sha256()
    for origin, targets in zip(origin_dates, target_dates, strict=True):
        digest.update(str(origin).encode())
        for target in targets:
            digest.update(str(target).encode())
    return digest.hexdigest()


def array_manifest(groups: Mapping[str, Mapping[str, NumericArray]]) -> dict[str, JsonValue]:
    manifest: dict[str, JsonValue] = {}
    for filename, arrays in groups.items():
        entries: dict[str, JsonValue] = {}
        for name, value in arrays.items():
            entries[name] = {"shape": list(value.shape), "dtype": value.dtype.str}
        manifest[filename] = entries
    return manifest
