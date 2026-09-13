from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from research.financial_jepa.artifacts import ArtifactBundle, write_bundle
from research.financial_jepa.contracts import (
    CollapseDiagnostics,
    Deadline,
    DevelopmentData,
    ExperimentConfig,
    JsonValue,
    PreparedSplits,
    RidgeModel,
    Scaler,
    WindowSet,
)
from research.financial_jepa.evaluation import (
    EvaluationResult,
    FrozenEvaluation,
    date_digest,
    diagnostics,
    evaluate_test,
    fit_direct_baseline,
    fit_readouts,
    metric_summary,
    predict_ridge,
)
from research.financial_jepa.model import build_model
from research.financial_jepa.protocol import PROTOCOL_VERSION, protocol_record
from research.financial_jepa.report import report_text
from research.financial_jepa.report_types import BaselineResults, FitOutcome, RidgeIdentity
from research.financial_jepa.reporting import results_record
from research.financial_jepa.training import train_variant


@dataclass(frozen=True, slots=True)
class ExperimentRequest:
    repo_root: Path
    output_dir: Path | None
    config: ExperimentConfig
    prepared: PreparedSplits
    source_metadata: Mapping[str, JsonValue]
    deadline: Deadline


def _checkpoint_diagnostic(
    frozen: FrozenEvaluation,
    data: WindowSet,
    scaler: Scaler,
    config: ExperimentConfig,
) -> CollapseDiagnostics:
    model = build_model(config, frozen.trained.seed)
    model.load_state_dict(frozen.trained.model_state)
    scaled = (data.unique_rows - scaler.mean) / scaler.std
    with torch.no_grad():
        encoded = model.target_encoder(torch.from_numpy(scaled).float()).numpy()
    return diagnostics(encoded.astype(np.float64))


def _ridge_identity(models: tuple[RidgeModel, ...], alpha: float) -> RidgeIdentity:
    coefficients = hashlib.sha256()
    scalers = hashlib.sha256()
    intercepts = hashlib.sha256()
    combined = hashlib.sha256(float(alpha).hex().encode())
    for model in models:
        coefficients.update(model.coefficients.tobytes())
        scalers.update(model.feature_mean.tobytes())
        scalers.update(model.feature_std.tobytes())
        intercepts.update(model.intercept.tobytes())
        for values in (
            model.feature_mean,
            model.feature_std,
            model.coefficients,
            model.intercept,
        ):
            combined.update(values.tobytes())
    return RidgeIdentity(
        coefficients.hexdigest(),
        scalers.hexdigest(),
        intercepts.hexdigest(),
        combined.hexdigest(),
    )


def _code_identity(repo_root: Path) -> dict[str, JsonValue]:
    digest = hashlib.sha256()
    paths = [
        *sorted(Path(__file__).parent.glob("*.py")),
        repo_root / "scripts/run_financial_jepa.py",
        repo_root / "uv.lock",
    ]
    files: dict[str, JsonValue] = {}
    for path in paths:
        relative = path.relative_to(repo_root).as_posix()
        content = path.read_bytes()
        file_digest = hashlib.sha256(content).hexdigest()
        files[relative] = file_digest
        digest.update(relative.encode())
        digest.update(content)
    return {"sha256": digest.hexdigest(), "files": files}


def _baselines(request: ExperimentRequest) -> BaselineResults:
    test = request.prepared.test
    actual = np.stack([window.raw_future for window in test.windows])
    persistence = np.stack(
        [
            np.repeat(window.raw_context[-1][None, :], request.config.future_length, axis=0)
            for window in test.windows
        ]
    )
    train_mean = request.prepared.train.unique_rows.mean(axis=0)
    mean_prediction = np.broadcast_to(train_mean, actual.shape)
    direct = fit_direct_baseline(
        request.prepared.train,
        request.prepared.validation,
        request.config,
    )
    direct_features = np.stack([window.context.reshape(-1) for window in test.windows])
    direct_prediction = predict_ridge(direct.model, direct_features).reshape(actual.shape)
    return BaselineResults(
        date_sha256=date_digest(test),
        persistence=metric_summary(actual, persistence),
        training_mean=metric_summary(actual, mean_prediction),
        direct_ridge=metric_summary(actual, direct_prediction),
        direct_alpha=direct.alpha,
        direct_identity=_ridge_identity((direct.model,), direct.alpha),
    )


def run_prepared_experiment(request: ExperimentRequest) -> Path:
    request.deadline.check()
    development = DevelopmentData(request.prepared.train, request.prepared.validation)
    trained = tuple(
        train_variant(development, request.config, variant, seed, request.deadline)
        for variant in request.config.variants
        for seed in request.config.seeds
    )
    frozen = tuple(
        fit_readouts(request.prepared.train, request.prepared.validation, result, request.config)
        for result in trained
    )
    baselines = _baselines(request)
    request.deadline.check()
    evaluation_rows: list[EvaluationResult] = []
    for item in frozen:
        request.deadline.check()
        evaluation_rows.append(evaluate_test(item, request.prepared.test, request.config))
    evaluations = tuple(evaluation_rows)
    fits: list[FitOutcome] = []
    for item, evaluation in zip(frozen, evaluations, strict=True):
        readout_identity = _ridge_identity(item.readouts, item.alpha)
        fits.append(
            FitOutcome(
                variant=item.trained.variant,
                seed=item.trained.seed,
                selected_epoch=item.trained.selected_epoch,
                validation_mse=item.trained.validation_mse,
                checkpoint_sha256=item.trained.state_sha256,
                ridge_alpha=item.alpha,
                readout_sha256=readout_identity.combined_sha256,
                readout_identity=readout_identity,
                evaluation=evaluation,
                train_diagnostic=_checkpoint_diagnostic(
                    item, request.prepared.train, request.prepared.scaler, request.config
                ),
                validation_diagnostic=_checkpoint_diagnostic(
                    item, request.prepared.validation, request.prepared.scaler, request.config
                ),
                test_diagnostic=_checkpoint_diagnostic(
                    item, request.prepared.test, request.prepared.scaler, request.config
                ),
            )
        )
    results, verdict = results_record(
        tuple(fits), baselines, request.config.variants, request.prepared
    )
    protocol = protocol_record(request.config)
    protocol_bytes = (json.dumps(protocol, indent=2, sort_keys=True) + "\n").encode()
    protocol_sha256 = hashlib.sha256(protocol_bytes).hexdigest()
    source_bytes = (
        json.dumps(request.source_metadata, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    run_metadata: dict[str, JsonValue] = {
        "actual_device": "cpu",
        "actual_intraop_threads": torch.get_num_threads(),
        "actual_interop_threads": torch.get_num_interop_threads(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "data_loader_workers": 0,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "protocol_sha256": protocol_sha256,
        "frozen_protocol_identity": {
            "protocol_version": PROTOCOL_VERSION,
            "protocol_sha256": protocol_sha256,
        },
        "source_metadata_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "code_identity": _code_identity(request.repo_root),
        "planned_fit_count": len(request.config.variants) * len(request.config.seeds),
        "observed_fit_count": len(fits),
        "planned_epochs_per_fit": request.config.epochs,
        "observed_training_epoch_count": len(fits) * request.config.epochs,
        "deadline_seconds": request.deadline.limit_seconds,
        "computation_preparation_elapsed_seconds": request.deadline.elapsed(),
        "deviations_from_exact_replication": [
            "eight official Treasury yield fields instead of 22 private equity features",
            "16 latent dimensions instead of the reported 64",
            "five future observations instead of the reported ten",
            "two predictor layers instead of the reported four-layer or six-layer descriptions",
            "ten epochs instead of the reported 50",
            "independent VICReg-style regularizer instead of SIGReg",
        ],
    }
    bundle = ArtifactBundle(
        protocol=protocol,
        source_metadata=request.source_metadata,
        results=results,
        report=report_text(tuple(fits), baselines, request.config.variants),
        run_metadata=run_metadata,
    )
    request.deadline.check()
    return write_bundle(request.repo_root, request.output_dir, bundle, request.deadline)
