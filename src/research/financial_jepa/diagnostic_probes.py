from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from research.financial_jepa.contracts import (
    CollapseDiagnostics,
    ExperimentConfig,
    FloatArray,
    MetricSummary,
    RidgeModel,
    WindowSet,
)
from research.financial_jepa.diagnostic_contracts import RecordedTrainResult
from research.financial_jepa.evaluation import diagnostics, fit_ridge, metric_summary, predict_ridge
from research.financial_jepa.model import build_model


@dataclass(frozen=True, slots=True)
class MethodFit:
    alpha: float
    models: tuple[RidgeModel, ...]
    validation_prediction: FloatArray
    metrics: MetricSummary


@dataclass(frozen=True, slots=True)
class SeedDiagnostics:
    seed: int
    selected_current: MethodFit
    predicted_future: MethodFit
    frozen_random_current: MethodFit
    selected_train_embeddings: FloatArray
    selected_validation_embeddings: FloatArray
    random_train_embeddings: FloatArray
    random_validation_embeddings: FloatArray
    predicted_validation_latents: FloatArray
    selected_validation_future_latents: FloatArray
    selected_validation_current_latents: FloatArray
    reconstruction: MethodFit


def raw_arrays(data: WindowSet) -> tuple[FloatArray, FloatArray]:
    features = np.stack([window.raw_context.reshape(-1) for window in data.windows])
    targets = np.stack([window.raw_future for window in data.windows])
    return features.astype(np.float64), targets.astype(np.float64)


def _shared_readouts(
    train_features: FloatArray,
    train_targets: FloatArray,
    validation_features: FloatArray,
    validation_targets: FloatArray,
    alphas: tuple[float, ...],
) -> MethodFit:
    selected_models: tuple[RidgeModel, ...] = ()
    selected_prediction = np.empty_like(validation_targets)
    selected_alpha = alphas[0]
    selected_mse = float("inf")
    for alpha in sorted(set(alphas)):
        models = tuple(
            fit_ridge(train_features[:, horizon], train_targets[:, horizon], alpha)
            if train_features.ndim == 3
            else fit_ridge(train_features, train_targets[:, horizon], alpha)
            for horizon in range(train_targets.shape[1])
        )
        prediction = np.stack(
            [
                predict_ridge(
                    models[horizon],
                    validation_features[:, horizon]
                    if validation_features.ndim == 3
                    else validation_features,
                )
                for horizon in range(validation_targets.shape[1])
            ],
            axis=1,
        )
        mse = float(np.mean((prediction - validation_targets) ** 2))
        if mse < selected_mse:
            selected_models = models
            selected_prediction = prediction
            selected_alpha = alpha
            selected_mse = mse
    return MethodFit(
        selected_alpha,
        selected_models,
        selected_prediction,
        metric_summary(validation_targets, selected_prediction),
    )


def fit_raw_history(
    train: WindowSet, validation: WindowSet, alphas: tuple[float, ...]
) -> MethodFit:
    train_features, train_targets = raw_arrays(train)
    validation_features, validation_targets = raw_arrays(validation)
    flattened_train = train_targets.reshape(len(train_targets), -1)
    flattened_validation = validation_targets.reshape(len(validation_targets), -1)
    best: RidgeModel | None = None
    best_prediction = np.empty_like(flattened_validation)
    best_mse = float("inf")
    for alpha in sorted(set(alphas)):
        model = fit_ridge(train_features, flattened_train, alpha)
        prediction = predict_ridge(model, validation_features)
        mse = float(np.mean((prediction - flattened_validation) ** 2))
        if mse < best_mse:
            best, best_prediction, best_mse = model, prediction, mse
    assert best is not None
    shaped = best_prediction.reshape(validation_targets.shape)
    return MethodFit(best.alpha, (best,), shaped, metric_summary(validation_targets, shaped))


def _model_features(
    state: dict[str, torch.Tensor], data: WindowSet, config: ExperimentConfig, seed: int
) -> tuple[FloatArray, FloatArray, FloatArray]:
    model = build_model(config, seed)
    model.load_state_dict(state)
    contexts = torch.from_numpy(np.stack([window.context for window in data.windows])).float()
    futures = torch.from_numpy(np.stack([window.future for window in data.windows])).float()
    model.eval()
    with torch.no_grad():
        current = model.target_encoder(contexts[:, -1])
        predicted = model.predict(contexts)
        future = model.encode_target(futures)
    return (
        current.numpy().astype(np.float64),
        predicted.numpy().astype(np.float64),
        future.numpy().astype(np.float64),
    )


def _row_embeddings(
    state: dict[str, torch.Tensor],
    data: WindowSet,
    scaler_mean: FloatArray,
    scaler_std: FloatArray,
    config: ExperimentConfig,
    seed: int,
) -> FloatArray:
    model = build_model(config, seed)
    model.load_state_dict(state)
    scaled = (data.unique_rows - scaler_mean) / scaler_std
    model.eval()
    with torch.no_grad():
        values = model.target_encoder(torch.from_numpy(scaled).float())
    return values.numpy().astype(np.float64)


def fit_seed_diagnostics(
    recorded: RecordedTrainResult,
    train: WindowSet,
    validation: WindowSet,
    scaler_mean: FloatArray,
    scaler_std: FloatArray,
    config: ExperimentConfig,
) -> SeedDiagnostics:
    selected_train_current, selected_train_predicted, _ = _model_features(
        recorded.result.model_state, train, config, recorded.result.seed
    )
    selected_validation_current, selected_validation_predicted, selected_validation_future = (
        _model_features(recorded.result.model_state, validation, config, recorded.result.seed)
    )
    random_train_current, _, _ = _model_features(
        recorded.initial_model_state, train, config, recorded.result.seed
    )
    random_validation_current, _, _ = _model_features(
        recorded.initial_model_state, validation, config, recorded.result.seed
    )
    train_targets = np.stack([window.raw_future for window in train.windows])
    validation_targets = np.stack([window.raw_future for window in validation.windows])
    repeated_train = np.repeat(selected_train_current[:, None, :], config.future_length, axis=1)
    repeated_validation = np.repeat(
        selected_validation_current[:, None, :], config.future_length, axis=1
    )
    repeated_random_train = np.repeat(
        random_train_current[:, None, :], config.future_length, axis=1
    )
    repeated_random_validation = np.repeat(
        random_validation_current[:, None, :], config.future_length, axis=1
    )
    selected_rows_train = _row_embeddings(
        recorded.result.model_state, train, scaler_mean, scaler_std, config, recorded.result.seed
    )
    selected_rows_validation = _row_embeddings(
        recorded.result.model_state,
        validation,
        scaler_mean,
        scaler_std,
        config,
        recorded.result.seed,
    )
    random_rows_train = _row_embeddings(
        recorded.initial_model_state, train, scaler_mean, scaler_std, config, recorded.result.seed
    )
    random_rows_validation = _row_embeddings(
        recorded.initial_model_state,
        validation,
        scaler_mean,
        scaler_std,
        config,
        recorded.result.seed,
    )
    reconstruction_targets_train = train.unique_rows[:, None, :]
    reconstruction_targets_validation = validation.unique_rows[:, None, :]
    return SeedDiagnostics(
        seed=recorded.result.seed,
        selected_current=_shared_readouts(
            repeated_train,
            train_targets,
            repeated_validation,
            validation_targets,
            config.ridge_alphas,
        ),
        predicted_future=_shared_readouts(
            selected_train_predicted,
            train_targets,
            selected_validation_predicted,
            validation_targets,
            config.ridge_alphas,
        ),
        frozen_random_current=_shared_readouts(
            repeated_random_train,
            train_targets,
            repeated_random_validation,
            validation_targets,
            config.ridge_alphas,
        ),
        selected_train_embeddings=selected_rows_train,
        selected_validation_embeddings=selected_rows_validation,
        random_train_embeddings=random_rows_train,
        random_validation_embeddings=random_rows_validation,
        predicted_validation_latents=selected_validation_predicted,
        selected_validation_future_latents=selected_validation_future,
        selected_validation_current_latents=repeated_validation,
        reconstruction=_shared_readouts(
            selected_rows_train[:, None, :],
            reconstruction_targets_train,
            selected_rows_validation[:, None, :],
            reconstruction_targets_validation,
            config.ridge_alphas,
        ),
    )


def representation_summary(values: FloatArray) -> tuple[tuple[float, ...], CollapseDiagnostics]:
    sample_std = np.std(values, axis=0, ddof=1)
    return tuple(float(value) for value in sample_std), diagnostics(values)
