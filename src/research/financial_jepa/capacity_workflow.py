from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from pydantic import JsonValue, TypeAdapter

from research.financial_jepa.capacity_fitting import run_trial
from research.financial_jepa.capacity_inputs import feature_pairs, load_input
from research.financial_jepa.capacity_reporting import render_report, summary
from research.financial_jepa.capacity_storage import load_bundle, write_bundle
from research.financial_jepa.capacity_validation import verify_capacity_bundle
from research.financial_jepa.contracts import ALPHAS, SEEDS, Deadline, FloatArray
from research.financial_jepa.walkforward_protocol import digest, preregister_folds


def run_capacity(repo_root: Path, source: Path, cache: Path) -> tuple[Path, Path]:
    deadline = Deadline.start(900)
    loaded = load_input(source, cache, deadline)
    protocol: dict[str, JsonValue] = {
        "version": "yield-jepa-capacity/1",
        "status": "development_selection",
        "input_readout_groups": {"current": [8, 8], "history": [240, 16]},
        "seeds": list(SEEDS),
        "ridge_alphas": list(ALPHAS),
        "deadline_seconds": 900,
        "selection": "source checkpoint and shared ridge alpha use 2018-2021; "
        "train preprocessing uses 2001-2017 only",
        "neural_fit_count": 0,
        "ridge_candidate_count": 360,
        "source_artifact_sha256": {name: value for name, value in loaded.source_hashes.items()},
    }
    trials = []
    arrays: dict[str, FloatArray] = {}
    for seed in SEEDS:
        deadline.check()
        for pair in feature_pairs(loaded, seed):
            deadline.check()
            trial, fitted = run_trial(pair)
            trials.append(trial)
            arrays.update(
                {f"seed_{seed}.{pair.name}.{key}": value for key, value in fitted.items()}
            )
    prepared = loaded.prepared
    membership: dict[str, JsonValue] = {
        "train_origin_dates": [window.origin_date.isoformat() for window in prepared.train.windows],
        "selection_origin_dates": [
            window.origin_date.isoformat() for window in prepared.validation.windows
        ],
        "train_target_dates": [
            [day.isoformat() for day in window.target_dates] for window in prepared.train.windows
        ],
        "selection_target_dates": [
            [day.isoformat() for day in window.target_dates]
            for window in prepared.validation.windows
        ],
    }
    arrays["actual_selection_targets"] = np.stack(
        [window.raw_future for window in prepared.validation.windows]
    )
    aggregates = summary(tuple(trials))
    code = sorted((repo_root / "src/research/financial_jepa").glob("*.py"))
    code.append(repo_root / "scripts/diagnose_jepa_capacity.py")
    code_hashes: dict[str, JsonValue] = {
        str(path.relative_to(repo_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in code
    }
    document: dict[str, JsonValue] = {
        "protocol": protocol,
        "protocol_sha256": digest(protocol),
        "membership": membership,
        "membership_sha256": digest(membership),
        "code_sha256": code_hashes,
        "trials": [
            TypeAdapter(dict[str, JsonValue]).validate_python(trial.model_dump(mode="json"))
            for trial in trials
        ],
        "aggregates": aggregates,
    }
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    capacity_path = repo_root / "output/financial-jepa-capacity" / run_id
    walkforward_path = repo_root / "output/financial-jepa-walkforward-preregistration" / run_id
    deadline.check()
    preregistered = preregister_folds(
        tuple(row.observed_on for row in (*prepared.train_rows, *prepared.validation_rows)),
        loaded.source_hashes["run-metadata.json"],
    )
    declaration = TypeAdapter(dict[str, JsonValue]).validate_python(
        preregistered.model_dump(mode="json")
    )
    published: list[Path] = []
    try:
        write_bundle(capacity_path, document, arrays, render_report(tuple(trials), aggregates))
        published.append(capacity_path)
        verify_capacity_bundle(capacity_path)
        write_bundle(
            walkforward_path,
            declaration,
            {},
            "# Walk-forward preregistration\n\nNot executed. Reserved 2022–2025 values "
            "were not opened. See document.json for hash-bound memberships and selection plans.\n",
        )
        published.append(walkforward_path)
        load_bundle(walkforward_path)
        deadline.check()
    except (OSError, ValueError, TimeoutError):
        for path in published:
            shutil.rmtree(path)
        raise
    return capacity_path, walkforward_path
