from __future__ import annotations

import numpy as np

from research.financial_jepa.capacity_models import FeaturePair, Trial
from research.financial_jepa.contracts import ALPHAS, FloatArray, ProtocolError
from research.financial_jepa.evaluation import fit_ridge, metric_summary, predict_ridge


def project_training(
    train: FloatArray, selection: FloatArray, dimensions: int
) -> tuple[FloatArray, FloatArray, dict[str, FloatArray]]:
    if train.ndim != 2 or selection.ndim != 2 or train.shape[1] != selection.shape[1]:
        raise ProtocolError("projection features must be aligned matrices")
    if dimensions > min(train.shape) or dimensions < 1:
        raise ProtocolError("projection dimension exceeds training capacity")
    if not np.isfinite(train).all() or not np.isfinite(selection).all():
        raise ProtocolError("projection features must be finite")
    mean, std = train.mean(axis=0), train.std(axis=0)
    std = np.where(std > 0, std, 1.0)
    centered = (train - mean) / std
    _, singular, components = np.linalg.svd(centered, full_matrices=False)
    components = components[:dimensions].copy()
    for row in components:
        if row[np.argmax(np.abs(row))] < 0:
            row *= -1
    return (
        centered @ components.T,
        ((selection - mean) / std) @ components.T,
        {
            "projection_mean": mean,
            "projection_std": std,
            "projection_components": components,
            "projection_variance_fraction": np.asarray(
                float((singular[:dimensions] ** 2).sum() / (singular**2).sum())
                if np.any(singular)
                else 0.0
            ),
        },
    )


def run_trial(pair: FeaturePair) -> tuple[Trial, dict[str, FloatArray]]:
    budget, dimensions = (8, 8) if pair.group == "current" else (240, 16)
    if pair.input_budget != budget:
        raise ProtocolError("declared input budget disagrees with comparison group")
    if pair.train_targets.ndim != 3 or pair.train_targets.shape[1:] != (5, 8):
        raise ProtocolError("capacity protocol requires five horizons and eight tenors")
    if pair.selection_targets.shape[1:] != (5, 8):
        raise ProtocolError("capacity selection targets disagree")
    base = Trial(
        method=pair.name,
        group=pair.group,
        seed=pair.seed,
        status="failed",
        input_budget=budget,
        readout_features=dimensions,
        readout_parameters=(dimensions + 1) * 5 * 8,
        train_rows=len(pair.train_targets),
        selection_rows=len(pair.selection_targets),
    )
    try:
        return _fit(pair, dimensions, base)
    except (ProtocolError, np.linalg.LinAlgError) as exc:
        return base.model_copy(update={"error": str(exc)}), {}


def _fit(pair: FeaturePair, dimensions: int, base: Trial) -> tuple[Trial, dict[str, FloatArray]]:
    train, selection = pair.train, pair.selection
    arrays: dict[str, FloatArray] = {}
    if train.ndim == 2 and pair.name != "raw_current":
        train, selection, arrays = project_training(train, selection, dimensions)
    if train.ndim == 2:
        train = np.repeat(train[:, None, :], 5, axis=1)
        selection = np.repeat(selection[:, None, :], 5, axis=1)
    if train.shape != (len(pair.train_targets), 5, dimensions) or selection.shape != (
        len(pair.selection_targets),
        5,
        dimensions,
    ):
        raise ProtocolError("readout features disagree with matched capacity")
    if not all(
        np.isfinite(value).all()
        for value in (train, selection, pair.train_targets, pair.selection_targets)
    ):
        raise ProtocolError("readout arrays must be finite")
    best = float("inf")
    selected: Trial | None = None
    best_arrays: dict[str, FloatArray] = {}
    for alpha in ALPHAS:
        models = tuple(fit_ridge(train[:, h], pair.train_targets[:, h], alpha) for h in range(5))
        forecast = np.stack(
            [predict_ridge(model, selection[:, h]) for h, model in enumerate(models)], axis=1
        )
        error = float(np.mean((forecast - pair.selection_targets) ** 2))
        if not np.isfinite(error):
            raise ProtocolError("readout forecast is nonfinite")
        if error < best:
            best = error
            metric = metric_summary(pair.selection_targets, forecast)
            selected = base.model_copy(
                update={
                    "status": "ok",
                    "selected_alpha": alpha,
                    "rmse_bp": metric.overall_rmse_bp,
                    "per_horizon_rmse_bp": metric.per_horizon_rmse_bp,
                    "projection_variance_retained": float(arrays["projection_variance_fraction"])
                    if arrays
                    else None,
                    "training_feature_rank": min(
                        int(np.linalg.matrix_rank(train[:, h] - train[:, h].mean(axis=0)))
                        for h in range(5)
                    ),
                }
            )
            best_arrays = {"forecast": forecast}
            for h, model in enumerate(models):
                best_arrays[f"ridge_{h}_coefficients"] = model.coefficients
                best_arrays[f"ridge_{h}_intercept"] = model.intercept
                best_arrays[f"ridge_{h}_mean"] = model.feature_mean
                best_arrays[f"ridge_{h}_std"] = model.feature_std
    if selected is None:
        raise ProtocolError("no finite fitted candidate")
    return selected, {**arrays, **best_arrays}
