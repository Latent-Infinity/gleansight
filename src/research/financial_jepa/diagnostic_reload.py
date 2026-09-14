from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from research.financial_jepa.contracts import (
    ExperimentConfig,
    FloatArray,
    JsonValue,
    ProtocolError,
    RidgeModel,
    Variant,
)
from research.financial_jepa.diagnostic_aggregate import verified_seed_aggregates
from research.financial_jepa.diagnostic_artifacts import (
    LoadedDiagnosticBundle,
    load_diagnostic_bundle,
)
from research.financial_jepa.diagnostic_capture import date_sha256
from research.financial_jepa.diagnostic_semantic import verify_semantic_artifacts
from research.financial_jepa.evaluation import metric_summary, predict_ridge
from research.financial_jepa.model import build_model
from research.financial_jepa.reporting import metric_record
from research.financial_jepa.training import state_digest


@dataclass(frozen=True, slots=True)
class ReloadVerification:
    bundle: LoadedDiagnosticBundle
    forecasts: dict[str, FloatArray]


def _mapping(value: JsonValue, name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ProtocolError(f"diagnostic {name} must be a JSON mapping")
    return value


def _sequence(value: JsonValue, name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ProtocolError(f"diagnostic {name} must be a JSON sequence")
    return value


def _integer(value: JsonValue, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolError(f"diagnostic {name} must be an integer")
    return value


def _number(value: JsonValue, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ProtocolError(f"diagnostic {name} must be numeric")
    return float(value)


def _config(bundle: LoadedDiagnosticBundle) -> ExperimentConfig:
    window = _mapping(bundle.protocol["window"], "window")
    training = _mapping(bundle.protocol["training"], "training")
    dataset = _mapping(bundle.protocol["dataset"], "dataset")
    methods = _mapping(bundle.protocol["methods"], "methods")
    years = tuple(_integer(value, "year") for value in _sequence(dataset["years"], "years"))
    seeds = tuple(_integer(value, "seed") for value in _sequence(training["seeds"], "seeds"))
    alphas = tuple(
        _number(value, "alpha") for value in _sequence(methods["alpha_grid"], "alpha grid")
    )
    return ExperimentConfig(
        label="development_selection",
        years=years,
        context_length=_integer(window["context"], "context"),
        future_length=_integer(window["future"], "future"),
        batch_size=_integer(training["batch_size"], "batch size"),
        epochs=_integer(training["epochs"], "epochs"),
        variants=(Variant.REGULARIZED,),
        seeds=seeds,
        ridge_alphas=alphas,
        deadline_seconds=900.0,
    )


def _state(bundle: LoadedDiagnosticBundle, seed: int, label: str) -> dict[str, torch.Tensor]:
    prefix = f"seed_{seed}.{label}."
    state = {
        name.removeprefix(prefix): torch.from_numpy(values.copy())
        for name, values in bundle.states.items()
        if name.startswith(prefix)
    }
    if not state:
        raise ProtocolError("diagnostic model state is missing")
    return state


def _ridge(bundle: LoadedDiagnosticBundle, prefix: str, index: int, alpha: float) -> RidgeModel:
    base = f"{prefix}.model_{index}"
    try:
        return RidgeModel(
            alpha,
            bundle.ridge[f"{base}.feature_mean"].astype(np.float64, copy=False),
            bundle.ridge[f"{base}.feature_std"].astype(np.float64, copy=False),
            bundle.ridge[f"{base}.coefficients"].astype(np.float64, copy=False),
            bundle.ridge[f"{base}.intercept"].astype(np.float64, copy=False),
        )
    except KeyError as exc:
        raise ProtocolError("diagnostic ridge state is missing") from exc


def _forecast_readouts(
    bundle: LoadedDiagnosticBundle,
    prefix: str,
    features: FloatArray,
    alpha: float,
    future_length: int,
) -> FloatArray:
    return np.stack(
        [
            predict_ridge(
                _ridge(bundle, prefix, horizon, alpha),
                features[:, horizon] if features.ndim == 3 else features,
            )
            for horizon in range(future_length)
        ],
        axis=1,
    )


def _verify_metric(actual: FloatArray, predicted: FloatArray, record: dict[str, JsonValue]) -> None:
    expected = metric_record(metric_summary(actual, predicted))
    observed = {key: value for key, value in record.items() if key != "shared_alpha"}
    if observed != expected:
        raise ProtocolError("diagnostic saved metrics do not match reconstructed forecasts")


def reload_and_verify(run_root: Path) -> ReloadVerification:
    bundle = load_diagnostic_bundle(run_root)
    config = _config(bundle)
    validation = bundle.validation
    scaled_contexts = validation["scaled_contexts"].astype(np.float64, copy=False)
    raw_contexts = validation["raw_contexts"].astype(np.float64, copy=False)
    actual = validation["raw_actual_future"].astype(np.float64, copy=False)
    if (
        date_sha256(validation["origin_dates"], validation["target_dates"])
        != bundle.results["date_sha256"]
    ):
        raise ProtocolError("diagnostic common date identity mismatch")
    result_methods = _mapping(bundle.results["methods"], "result methods")
    raw_record = _mapping(result_methods["raw_history"], "raw history")
    raw_alpha = _number(raw_record["shared_alpha"], "raw alpha")
    raw_flat = predict_ridge(
        _ridge(bundle, "raw_history", 0, raw_alpha),
        raw_contexts.reshape(len(raw_contexts), -1),
    )
    raw_forecast = raw_flat.reshape(actual.shape)
    persistence = np.repeat(raw_contexts[:, -1:, :], config.future_length, axis=1)
    forecasts: dict[str, FloatArray] = {
        "raw_history": raw_forecast,
        "persistence": persistence,
    }
    _verify_metric(actual, raw_forecast, raw_record)
    _verify_metric(actual, persistence, _mapping(bundle.results["persistence"], "persistence"))
    verified_seed_rows: list[dict[str, JsonValue]] = []
    for seed_value in _sequence(bundle.results["seeds"], "result seeds"):
        seed_row = _mapping(seed_value, "seed result")
        seed = _integer(seed_row["seed"], "seed")
        methods = _mapping(seed_row["methods"], "seed methods")
        selected_state = _state(bundle, seed, "selected")
        initial_state = _state(bundle, seed, "initial")
        if state_digest(selected_state) != seed_row["selected_state_sha256"]:
            raise ProtocolError("diagnostic selected state digest mismatch")
        if state_digest(initial_state) != seed_row["initial_state_sha256"]:
            raise ProtocolError("diagnostic initial state digest mismatch")
        selected_model = build_model(config, seed)
        selected_model.load_state_dict(selected_state)
        random_model = build_model(config, seed)
        random_model.load_state_dict(initial_state)
        contexts = torch.from_numpy(scaled_contexts).float()
        selected_model.eval()
        random_model.eval()
        with torch.no_grad():
            selected_current = (
                selected_model.target_encoder(contexts[:, -1]).numpy().astype(np.float64)
            )
            predicted = selected_model.predict(contexts).numpy().astype(np.float64)
            random_current = random_model.target_encoder(contexts[:, -1]).numpy().astype(np.float64)
        validation_selected_rows = verify_semantic_artifacts(
            bundle,
            config,
            seed,
            seed_row,
            selected_model,
            random_model,
            selected_current,
            predicted,
            actual,
        )
        feature_sets = {
            "selected_ema_current": np.repeat(
                selected_current[:, None, :], config.future_length, axis=1
            ),
            "predicted_future": predicted,
            "frozen_random_current": np.repeat(
                random_current[:, None, :], config.future_length, axis=1
            ),
        }
        for name, features in feature_sets.items():
            record = _mapping(methods[name], name)
            prediction = _forecast_readouts(
                bundle,
                f"seed_{seed}.{name}",
                features,
                _number(record["shared_alpha"], f"{name} alpha"),
                config.future_length,
            )
            saved = validation[f"forecast.seed_{seed}.{name}"].astype(np.float64, copy=False)
            if not np.array_equal(prediction, saved):
                raise ProtocolError("diagnostic reconstructed forecast differs from saved forecast")
            forecasts[f"seed_{seed}.{name}"] = prediction
            _verify_metric(actual, prediction, record)
        reconstruction_record = _mapping(
            seed_row["current_reconstruction"], "current reconstruction"
        )
        reconstruction = predict_ridge(
            _ridge(
                bundle,
                f"seed_{seed}.current_reconstruction",
                0,
                _number(reconstruction_record["shared_alpha"], "reconstruction alpha"),
            ),
            validation_selected_rows,
        )
        saved_reconstruction = validation[f"reconstruction.seed_{seed}.selected_ema"]
        if not np.array_equal(reconstruction, saved_reconstruction):
            raise ProtocolError("diagnostic reconstructed current yields differ from saved values")
        _verify_metric(
            validation["validation_raw_rows"].astype(np.float64, copy=False)[:, None, :],
            reconstruction[:, None, :],
            reconstruction_record,
        )
        verified_seed_rows.append(seed_row)
    if verified_seed_aggregates(verified_seed_rows) != _mapping(
        bundle.results["aggregates"], "aggregates"
    ):
        raise ProtocolError("diagnostic seed aggregates do not match reconstructed seed results")
    if not np.array_equal(raw_forecast, validation["forecast.raw_history"]):
        raise ProtocolError("diagnostic reconstructed raw forecast differs from saved forecast")
    if not np.array_equal(persistence, validation["forecast.persistence"]):
        raise ProtocolError("diagnostic reconstructed persistence differs from saved forecast")
    return ReloadVerification(bundle, forecasts)
