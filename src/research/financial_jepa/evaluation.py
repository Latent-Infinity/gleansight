from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import torch

from research.financial_jepa.contracts import (
    CollapseDiagnostics,
    ExperimentConfig,
    FloatArray,
    MetricSummary,
    ProtocolError,
    RidgeData,
    RidgeModel,
    TrainResult,
    WindowSet,
)
from research.financial_jepa.model import build_model


@dataclass(frozen=True, slots=True)
class FrozenEvaluation:
    trained: TrainResult
    alpha: float
    readouts: tuple[RidgeModel, ...]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    raw_metrics: MetricSummary
    latent_mse: float
    latent_persistence_mse: float
    date_sha256: str


@dataclass(frozen=True, slots=True)
class DirectBaseline:
    alpha: float
    model: RidgeModel
    future_length: int


def fit_ridge(features: FloatArray, targets: FloatArray, alpha: float) -> RidgeModel:
    if features.ndim != 2 or targets.ndim != 2 or len(features) != len(targets):
        raise ProtocolError("ridge arrays must be aligned two-dimensional matrices")
    feature_mean = features.mean(axis=0)
    observed_std = features.std(axis=0, ddof=0)
    if not np.isfinite(observed_std).all():
        raise ProtocolError("ridge training features have invalid standard deviation")
    active = observed_std > 0.0
    feature_std = np.where(active, observed_std, 1.0)
    standardized = (features - feature_mean) / feature_std
    target_mean = targets.mean(axis=0)
    centered_targets = targets - target_mean
    standardized_coefficients = np.zeros((features.shape[1], targets.shape[1]), dtype=np.float64)
    if np.any(active):
        active_features = standardized[:, active]
        penalty = len(features) * alpha * np.eye(active_features.shape[1], dtype=np.float64)
        standardized_coefficients[active] = np.linalg.solve(
            active_features.T @ active_features + penalty,
            active_features.T @ centered_targets,
        )
    coefficients = standardized_coefficients / feature_std[:, None]
    intercept = target_mean - feature_mean @ coefficients
    return RidgeModel(alpha, feature_mean, feature_std, coefficients, intercept)


def predict_ridge(model: RidgeModel, features: FloatArray) -> FloatArray:
    return features @ model.coefficients + model.intercept


def select_ridge(
    train: RidgeData,
    validation: RidgeData,
    alphas: tuple[float, ...],
) -> RidgeModel:
    selected: RidgeModel | None = None
    selected_mse = float("inf")
    for alpha in sorted(set(alphas)):
        candidate = fit_ridge(train.features, train.targets, alpha)
        prediction = predict_ridge(candidate, validation.features)
        mse = float(np.mean((prediction - validation.targets) ** 2))
        if mse < selected_mse:
            selected = candidate
            selected_mse = mse
    if selected is None:
        raise ProtocolError("ridge alpha grid is empty")
    return selected


def metric_summary(actual: FloatArray, predicted: FloatArray) -> MetricSummary:
    if actual.shape != predicted.shape or actual.ndim != 3:
        raise ProtocolError("forecast arrays must share [sample,horizon,tenor] shape")
    squared = (actual - predicted) ** 2
    overall = 100.0 * float(np.sqrt(squared.mean()))
    per_horizon = tuple(float(value) for value in 100.0 * np.sqrt(squared.mean(axis=(0, 2))))
    per_tenor = tuple(float(value) for value in 100.0 * np.sqrt(squared.mean(axis=(0, 1))))
    matrix = tuple(
        tuple(float(value) for value in row) for row in 100.0 * np.sqrt(squared.mean(axis=0))
    )
    return MetricSummary(overall, per_horizon, per_tenor, matrix)


def diagnostics(embeddings: FloatArray) -> CollapseDiagnostics:
    sample_std = np.std(embeddings, axis=0, ddof=1) if len(embeddings) > 1 else np.zeros(16)
    mean_std = float(np.mean(sample_std))
    covariance = (
        np.cov(embeddings, rowvar=False, ddof=1) if len(embeddings) > 1 else np.zeros((16, 16))
    )
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
    trace = float(eigenvalues.sum())
    if trace <= 1e-12:
        effective_rank = 0.0
    else:
        probabilities = eigenvalues[eigenvalues > 0.0] / trace
        effective_rank = float(np.exp(-np.sum(probabilities * np.log(probabilities))))
    return CollapseDiagnostics(mean_std, effective_rank, mean_std < 0.1 or effective_rank < 2.0)


def date_digest(data: WindowSet) -> str:
    digest = hashlib.sha256()
    for window in data.windows:
        digest.update(window.origin_date.isoformat().encode())
        for target_date in window.target_dates:
            digest.update(target_date.isoformat().encode())
    return digest.hexdigest()


def _model_arrays(
    data: WindowSet,
    trained: TrainResult,
    config: ExperimentConfig,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    model = build_model(config, trained.seed)
    model.load_state_dict(trained.model_state)
    contexts = torch.from_numpy(np.stack([window.context for window in data.windows])).float()
    futures = torch.from_numpy(np.stack([window.future for window in data.windows])).float()
    model.eval()
    with torch.no_grad():
        predictions = model.predict(contexts)
        targets = model.encode_target(futures)
        persistence = model.target_encoder(contexts[:, -1, :]).unsqueeze(1).expand_as(targets)
    return (
        predictions.numpy().astype(np.float64),
        targets.numpy().astype(np.float64),
        persistence.numpy().astype(np.float64),
    )


def fit_readouts(
    train: WindowSet,
    validation: WindowSet,
    trained: TrainResult,
    config: ExperimentConfig,
) -> FrozenEvaluation:
    train_predictions, _, _ = _model_arrays(train, trained, config)
    validation_predictions, _, _ = _model_arrays(validation, trained, config)
    train_targets = np.stack([window.raw_future for window in train.windows])
    validation_targets = np.stack([window.raw_future for window in validation.windows])
    selected_alpha = config.ridge_alphas[0]
    selected_mse = float("inf")
    selected_readouts: tuple[RidgeModel, ...] = ()
    for alpha in config.ridge_alphas:
        readouts = tuple(
            fit_ridge(train_predictions[:, horizon, :], train_targets[:, horizon, :], alpha)
            for horizon in range(config.future_length)
        )
        prediction = np.stack(
            [
                predict_ridge(readouts[horizon], validation_predictions[:, horizon, :])
                for horizon in range(config.future_length)
            ],
            axis=1,
        )
        mse = float(np.mean((prediction - validation_targets) ** 2))
        if mse < selected_mse:
            selected_alpha = alpha
            selected_mse = mse
            selected_readouts = readouts
    return FrozenEvaluation(trained, selected_alpha, selected_readouts)


def evaluate_test(
    frozen: FrozenEvaluation,
    test: WindowSet,
    config: ExperimentConfig,
) -> EvaluationResult:
    predictions, targets, persistence = _model_arrays(test, frozen.trained, config)
    raw_actual = np.stack([window.raw_future for window in test.windows])
    raw_prediction = np.stack(
        [
            predict_ridge(frozen.readouts[horizon], predictions[:, horizon, :])
            for horizon in range(config.future_length)
        ],
        axis=1,
    )
    return EvaluationResult(
        raw_metrics=metric_summary(raw_actual, raw_prediction),
        latent_mse=float(np.mean((predictions - targets) ** 2)),
        latent_persistence_mse=float(np.mean((persistence - targets) ** 2)),
        date_sha256=date_digest(test),
    )


def fit_direct_baseline(
    train: WindowSet,
    validation: WindowSet,
    config: ExperimentConfig,
) -> DirectBaseline:
    train_data = RidgeData(
        np.stack([window.context.reshape(-1) for window in train.windows]),
        np.stack([window.raw_future.reshape(-1) for window in train.windows]),
    )
    validation_data = RidgeData(
        np.stack([window.context.reshape(-1) for window in validation.windows]),
        np.stack([window.raw_future.reshape(-1) for window in validation.windows]),
    )
    model = select_ridge(train_data, validation_data, config.ridge_alphas)
    return DirectBaseline(model.alpha, model, config.future_length)
