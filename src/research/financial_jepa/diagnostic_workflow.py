from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import torch
from pydantic import TypeAdapter

from research.financial_jepa.contracts import (
    Deadline,
    DevelopmentData,
    JsonValue,
    Variant,
)
from research.financial_jepa.diagnostic_aggregate import seed_aggregates
from research.financial_jepa.diagnostic_artifacts import DiagnosticBundle, write_diagnostic_bundle
from research.financial_jepa.diagnostic_capture import (
    array_manifest,
    date_sha256,
    ridge_arrays,
    seed_record,
    state_arrays,
    validation_arrays,
)
from research.financial_jepa.diagnostic_contracts import (
    DiagnosticConfig,
    PreparedDevelopment,
)
from research.financial_jepa.diagnostic_guard import validate_diagnostic_request
from research.financial_jepa.diagnostic_probes import (
    fit_raw_history,
    fit_seed_diagnostics,
    representation_summary,
)
from research.financial_jepa.diagnostic_reporting import (
    code_identity,
    diagnostic_protocol,
    report_text,
)
from research.financial_jepa.evaluation import metric_summary
from research.financial_jepa.reporting import metric_record
from research.financial_jepa.training import train_variant_recorded

_JSON_RECORD_ADAPTER: Final = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True, slots=True)
class PreparedDiagnosticRequest:
    repo_root: Path
    output_dir: Path | None
    config: DiagnosticConfig
    prepared: PreparedDevelopment
    source_metadata: dict[str, JsonValue]
    deadline: Deadline


def _raw_representation(values: np.ndarray) -> dict[str, JsonValue]:
    per_dimension, summary = representation_summary(values)
    return _JSON_RECORD_ADAPTER.validate_python(
        {
            "per_dimension_sample_std": list(per_dimension),
            "mean_sample_std": summary.mean_sample_std,
            "covariance_effective_rank": summary.effective_rank,
        }
    )


def run_prepared_diagnostics(request: PreparedDiagnosticRequest) -> Path:
    request.deadline.check()
    validate_diagnostic_request(
        request.config,
        request.prepared,
        request.output_dir,
        request.deadline.limit_seconds,
    )
    config = request.config.training_config()
    development = DevelopmentData(request.prepared.train, request.prepared.validation)
    recorded = tuple(
        train_variant_recorded(development, config, Variant.REGULARIZED, seed, request.deadline)
        for seed in request.config.seeds
    )
    seed_diagnostics = tuple(
        fit_seed_diagnostics(
            item,
            request.prepared.train,
            request.prepared.validation,
            request.prepared.scaler.mean,
            request.prepared.scaler.std,
            config,
        )
        for item in recorded
    )
    raw = fit_raw_history(
        request.prepared.train, request.prepared.validation, request.config.ridge_alphas
    )
    validation = request.prepared.validation
    contexts = np.stack([window.context for window in validation.windows])
    raw_contexts = np.stack([window.raw_context for window in validation.windows])
    actual = np.stack([window.raw_future for window in validation.windows])
    persistence = np.stack(
        [
            np.repeat(window.raw_context[-1][None, :], config.future_length, axis=0)
            for window in validation.windows
        ]
    )
    origins = np.asarray(
        [window.origin_date.isoformat() for window in validation.windows], dtype="U10"
    )
    targets = np.asarray(
        [[day.isoformat() for day in window.target_dates] for window in validation.windows],
        dtype="U10",
    )
    states = state_arrays(recorded)
    ridges = ridge_arrays(
        raw, seed_diagnostics, request.prepared.scaler.mean, request.prepared.scaler.std
    )
    validations = validation_arrays(
        contexts,
        raw_contexts,
        actual,
        origins,
        targets,
        raw,
        persistence,
        seed_diagnostics,
        validation.unique_rows,
        (validation.unique_rows - request.prepared.scaler.mean) / request.prepared.scaler.std,
        request.prepared.train.unique_rows,
        np.asarray(
            [row.observed_on.isoformat() for row in request.prepared.train_rows], dtype="U10"
        ),
        np.asarray(
            [row.observed_on.isoformat() for row in request.prepared.validation_rows], dtype="U10"
        ),
    )
    array_groups = {"states.npz": states, "ridge.npz": ridges, "validation.npz": validations}
    seed_rows: list[JsonValue] = [
        seed_record(item, values) for item, values in zip(recorded, seed_diagnostics, strict=True)
    ]
    results: dict[str, JsonValue] = {
        "status": request.config.label,
        "date_sha256": date_sha256(origins, targets),
        "methods": {
            "raw_history": {**metric_record(raw.metrics), "shared_alpha": raw.alpha},
            "raw_representations": {
                "train": _raw_representation(request.prepared.train.unique_rows),
                "validation": _raw_representation(validation.unique_rows),
            },
        },
        "seeds": seed_rows,
        "aggregates": seed_aggregates(seed_diagnostics),
        "persistence": metric_record(metric_summary(actual, persistence)),
        "array_manifest": array_manifest(array_groups),
    }
    protocol = diagnostic_protocol(request.config)
    protocol_bytes = (json.dumps(protocol, indent=2, sort_keys=True) + "\n").encode()
    source_bytes = (json.dumps(request.source_metadata, indent=2, sort_keys=True) + "\n").encode()
    runtime: dict[str, JsonValue] = {
        "device": "cpu",
        "intraop_threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "pid": os.getpid(),
        "environment": {
            "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
            "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS"),
        },
        "elapsed_seconds_before_artifacts": request.deadline.elapsed(),
        "deadline_seconds": request.deadline.limit_seconds,
    }
    metadata: dict[str, JsonValue] = {
        "runtime": runtime,
        "code_identity": code_identity(request.repo_root),
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "source_metadata_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "planned_fit_count": len(request.config.seeds),
        "observed_fit_count": len(recorded),
        "planned_epoch_count": len(request.config.seeds) * request.config.epochs,
        "observed_epoch_count": sum(len(item.epochs) for item in recorded),
    }
    request.deadline.check()
    return write_diagnostic_bundle(
        request.repo_root,
        request.output_dir,
        DiagnosticBundle(
            protocol,
            request.source_metadata,
            results,
            states,
            ridges,
            validations,
            report_text(results),
            metadata,
        ),
        request.deadline,
    )
