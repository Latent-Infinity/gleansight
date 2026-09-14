from __future__ import annotations

import numpy as np
import torch

from research.financial_jepa.contracts import ExperimentConfig, FloatArray, JsonValue, ProtocolError
from research.financial_jepa.diagnostic_artifacts import LoadedDiagnosticBundle
from research.financial_jepa.diagnostic_probes import representation_summary
from research.financial_jepa.model import YieldJepa


def _mapping(value: JsonValue, name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ProtocolError(f"diagnostic {name} must be a JSON mapping")
    return value


def _representation_record(values: FloatArray) -> dict[str, JsonValue]:
    per_dimension, summary = representation_summary(values)
    dimensions: list[JsonValue] = [float(value) for value in per_dimension]
    return {
        "per_dimension_sample_std": dimensions,
        "mean_sample_std": summary.mean_sample_std,
        "covariance_effective_rank": summary.effective_rank,
    }


def _require_array(expected: FloatArray, observed: np.ndarray, kind: str) -> None:
    if not np.array_equal(expected, observed.astype(np.float64, copy=False)):
        raise ProtocolError(f"diagnostic semantic {kind} differs from reconstructed state")


def verify_semantic_artifacts(
    bundle: LoadedDiagnosticBundle,
    config: ExperimentConfig,
    seed: int,
    seed_row: dict[str, JsonValue],
    selected_model: YieldJepa,
    random_model: YieldJepa,
    selected_current: FloatArray,
    predicted: FloatArray,
    actual: FloatArray,
) -> FloatArray:
    validation = bundle.validation
    mean = bundle.ridge["dataset_scaler.mean"].astype(np.float64, copy=False)
    std = bundle.ridge["dataset_scaler.std"].astype(np.float64, copy=False)
    train_scaled = (validation["train_raw_rows"].astype(np.float64, copy=False) - mean) / std
    validation_scaled = (
        validation["validation_raw_rows"].astype(np.float64, copy=False) - mean
    ) / std
    _require_array(
        validation_scaled,
        validation["validation_scaled_rows"],
        "representation scaler input",
    )
    with torch.no_grad():
        future = (
            selected_model.encode_target(torch.from_numpy((actual - mean) / std).float())
            .numpy()
            .astype(np.float64)
        )
        selected_train = (
            selected_model.target_encoder(torch.from_numpy(train_scaled).float())
            .numpy()
            .astype(np.float64)
        )
        selected_validation = (
            selected_model.target_encoder(torch.from_numpy(validation_scaled).float())
            .numpy()
            .astype(np.float64)
        )
        random_train = (
            random_model.target_encoder(torch.from_numpy(train_scaled).float())
            .numpy()
            .astype(np.float64)
        )
        random_validation = (
            random_model.target_encoder(torch.from_numpy(validation_scaled).float())
            .numpy()
            .astype(np.float64)
        )
    current = np.repeat(selected_current[:, None, :], config.future_length, axis=1)
    for name, expected in (
        ("predicted_future", predicted),
        ("ema_future", future),
        ("ema_current", current),
    ):
        _require_array(expected, validation[f"latent.seed_{seed}.{name}"], "latent")
    latent = _mapping(seed_row["latent"], "latent metrics")
    predicted_error = (predicted - future) ** 2
    persistence_error = (current - future) ** 2
    expected_latent: dict[str, JsonValue] = {
        "predicted_future_overall_mse": float(predicted_error.mean()),
        "predicted_future_per_horizon_mse": [
            float(value) for value in predicted_error.mean(axis=(0, 2))
        ],
        "ema_current_persistence_overall_mse": float(persistence_error.mean()),
        "ema_current_persistence_per_horizon_mse": [
            float(value) for value in persistence_error.mean(axis=(0, 2))
        ],
    }
    if latent != expected_latent:
        raise ProtocolError("diagnostic semantic latent metrics differ from reconstructed state")
    representations = _mapping(seed_row["representations"], "representations")
    for artifact, record, expected in (
        ("train_selected", "train_selected_ema", selected_train),
        ("validation_selected", "validation_selected_ema", selected_validation),
        ("train_random", "train_frozen_random", random_train),
        ("validation_random", "validation_frozen_random", random_validation),
    ):
        _require_array(
            expected,
            validation[f"representation.seed_{seed}.{artifact}"],
            "representation",
        )
        if _mapping(representations[record], record) != _representation_record(expected):
            raise ProtocolError(
                "diagnostic semantic representation metrics differ from reconstructed state"
            )
    return selected_validation
