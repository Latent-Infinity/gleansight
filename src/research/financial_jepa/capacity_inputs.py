from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from pydantic import TypeAdapter

from research.financial_jepa.capacity_models import FeaturePair
from research.financial_jepa.capacity_storage import bounded_read
from research.financial_jepa.contracts import Deadline, FloatArray, ProtocolError, WindowSet
from research.financial_jepa.dataset import prepare_development
from research.financial_jepa.diagnostic_artifacts import ARTIFACT_FILES, LoadedDiagnosticBundle
from research.financial_jepa.diagnostic_contracts import DiagnosticConfig, PreparedDevelopment
from research.financial_jepa.diagnostic_reload import reload_and_verify
from research.financial_jepa.diagnostic_reporting import diagnostic_protocol
from research.financial_jepa.model import build_model
from research.financial_jepa.treasury import (
    AcquisitionRequest,
    CacheMetadata,
    acquire_years,
    parse_years,
)


@dataclass(frozen=True, slots=True)
class CapacityInput:
    bundle: LoadedDiagnosticBundle
    prepared: PreparedDevelopment
    source_hashes: dict[str, str]


def load_input(bundle_path: Path, data_dir: Path, deadline: Deadline) -> CapacityInput:
    hashes = {
        name: hashlib.sha256(bounded_read(bundle_path / name)).hexdigest()
        for name in (*ARTIFACT_FILES, "run-metadata.json")
    }
    bundle = reload_and_verify(bundle_path).bundle
    config = DiagnosticConfig()
    validate_selection_protocol(bundle)
    receipt = acquire_years(AcquisitionRequest(config.training_config(), data_dir, True, deadline))
    recorded = TypeAdapter(list[CacheMetadata]).validate_python(
        bundle.source_metadata["yearly_responses"]
    )
    if {(row.year, row.sha256) for row in recorded} != {
        (row.year, row.sha256) for row in receipt.metadata
    }:
        raise ProtocolError("capacity source cache identity disagrees with selection provenance")
    parsed = parse_years(receipt.files)
    prepared = prepare_development(parsed.rows, config.training_config())
    validate_membership(bundle, prepared)
    if any(
        hashlib.sha256(bounded_read(bundle_path / name)).hexdigest() != value
        for name, value in hashes.items()
    ):
        raise ProtocolError("source selection artifacts changed during verification")
    return CapacityInput(bundle, prepared, hashes)


def validate_selection_protocol(bundle: LoadedDiagnosticBundle) -> None:
    if (
        bundle.protocol != diagnostic_protocol(DiagnosticConfig())
        or bundle.results.get("status") != "development_selection"
    ):
        raise ProtocolError("capacity source must use the frozen development selection protocol")


def validate_membership(bundle: LoadedDiagnosticBundle, prepared: PreparedDevelopment) -> None:
    for windows, lower, upper in ((prepared.train, 2001, 2017), (prepared.validation, 2018, 2021)):
        if any(
            day.year < lower or day.year > upper
            for window in windows.windows
            for day in (*window.context_dates, *window.target_dates)
        ):
            raise ProtocolError("capacity source contains reserved or cross-partition dates")
    values = bundle.validation
    expected = {
        "train_raw_rows": prepared.train.unique_rows,
        "validation_raw_rows": prepared.validation.unique_rows,
        "train_row_dates": np.asarray([row.observed_on.isoformat() for row in prepared.train_rows]),
        "validation_row_dates": np.asarray(
            [row.observed_on.isoformat() for row in prepared.validation_rows]
        ),
        "raw_contexts": np.stack([window.raw_context for window in prepared.validation.windows]),
        "raw_actual_future": np.stack(
            [window.raw_future for window in prepared.validation.windows]
        ),
        "origin_dates": np.asarray(
            [window.origin_date.isoformat() for window in prepared.validation.windows]
        ),
        "target_dates": np.asarray(
            [
                [day.isoformat() for day in window.target_dates]
                for window in prepared.validation.windows
            ]
        ),
    }
    if any(not np.array_equal(values[name], array) for name, array in expected.items()):
        raise ProtocolError("source selection dates, targets or context schema disagree")
    if not np.array_equal(
        bundle.ridge["dataset_scaler.mean"], prepared.scaler.mean
    ) or not np.array_equal(bundle.ridge["dataset_scaler.std"], prepared.scaler.std):
        raise ProtocolError("source train-only preprocessing disagrees")


def model_features(
    source: CapacityInput, seed: int, state_label: str, windows: WindowSet
) -> tuple[FloatArray, FloatArray]:
    prefix = f"seed_{seed}.{state_label}."
    state = {
        key.removeprefix(prefix): torch.from_numpy(value.copy())
        for key, value in source.bundle.states.items()
        if key.startswith(prefix)
    }
    if not state:
        raise ProtocolError("paired seed selection state is missing")
    model = build_model(DiagnosticConfig().training_config(), seed)
    model.load_state_dict(state)
    model.eval()
    current, predicted = [], []
    with torch.no_grad():
        for start in range(0, len(windows.windows), 128):
            contexts = torch.from_numpy(
                np.stack([window.context for window in windows.windows[start : start + 128]])
            ).float()
            current.append(model.target_encoder(contexts[:, -1]).numpy().astype(np.float64))
            predicted.append(model.predict(contexts).numpy().astype(np.float64))
    return np.concatenate(current), np.concatenate(predicted)


def feature_pairs(source: CapacityInput, seed: int) -> tuple[FeaturePair, ...]:
    if seed not in DiagnosticConfig().seeds:
        raise ProtocolError("capacity paired seed is not predeclared")
    prepared = source.prepared
    training = np.stack([window.raw_context for window in prepared.train.windows])
    selection = np.stack([window.raw_context for window in prepared.validation.windows])
    train_targets = np.stack([window.raw_future for window in prepared.train.windows])
    selection_targets = np.stack([window.raw_future for window in prepared.validation.windows])
    pairs = [
        FeaturePair(
            "raw_current",
            "current",
            seed,
            8,
            training[:, -1],
            selection[:, -1],
            train_targets,
            selection_targets,
        ),
        FeaturePair(
            "raw_history_pca",
            "history",
            seed,
            240,
            training.reshape(len(training), -1),
            selection.reshape(len(selection), -1),
            train_targets,
            selection_targets,
        ),
    ]
    for label, name in (("selected", "selected"), ("initial", "random")):
        train_current, train_predicted = model_features(source, seed, label, prepared.train)
        selection_current, selection_predicted = model_features(
            source, seed, label, prepared.validation
        )
        pairs.extend(
            (
                FeaturePair(
                    f"{name}_current_pca",
                    "current",
                    seed,
                    8,
                    train_current,
                    selection_current,
                    train_targets,
                    selection_targets,
                ),
                FeaturePair(
                    f"{name}_predicted",
                    "history",
                    seed,
                    240,
                    train_predicted,
                    selection_predicted,
                    train_targets,
                    selection_targets,
                ),
            )
        )
    return tuple(pairs)
