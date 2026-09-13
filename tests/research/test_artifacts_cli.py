from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from research.financial_jepa import artifacts
from research.financial_jepa.artifacts import ArtifactBundle, write_bundle
from research.financial_jepa.contracts import (
    Deadline,
    DeadlineExceededError,
    ExperimentConfig,
    ProtocolError,
    YieldRow,
)
from research.financial_jepa.dataset import prepare_splits
from research.financial_jepa.experiment import ExperimentRequest, run_prepared_experiment
from tests.research.support import curve

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_financial_jepa.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "UV_NO_SYNC": "1"}
    return subprocess.run(
        [str(REPO_ROOT / ".venv/bin/python"), str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_bundle_writes_finite_atomic_artifacts_and_completion_last(tmp_path: Path) -> None:
    output = tmp_path / "run"
    bundle = ArtifactBundle(
        protocol={"schema_version": 1},
        source_metadata={"license_expression": "NOASSERTION"},
        results={"rmse": 1.0},
        report="# YieldJEPA\n",
        run_metadata={"workflow": "financial-jepa"},
    )

    write_bundle(REPO_ROOT, output, bundle)

    assert {path.name for path in output.iterdir()} == {
        "protocol.json",
        "source-metadata.json",
        "results.json",
        "report.md",
        "run-metadata.json",
    }
    metadata = json.loads((output / "run-metadata.json").read_text())
    assert "completed_at_utc" not in metadata
    assert metadata["completion_marker_write_started_at_utc"].endswith("Z")
    for name, digest in metadata["artifact_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert not list(output.glob("*.tmp"))


def test_bundle_rejects_nonfinite_json_and_cleans_new_output(tmp_path: Path) -> None:
    output = tmp_path / "failed"
    bundle = ArtifactBundle({}, {}, {"bad": float("nan")}, "report", {})

    with pytest.raises(ProtocolError):
        write_bundle(REPO_ROOT, output, bundle)

    assert not output.exists()


def test_deadline_raises_typed_error() -> None:
    deadline = Deadline(started_monotonic=10.0, limit_seconds=1.0)

    with pytest.raises(DeadlineExceededError):
        deadline.check(now_monotonic=11.1)


def test_bundle_deadline_removes_incomplete_output(tmp_path: Path) -> None:
    output = tmp_path / "expired-bundle"
    bundle = ArtifactBundle({}, {}, {}, "report", {})

    with pytest.raises(DeadlineExceededError):
        write_bundle(
            REPO_ROOT,
            output,
            bundle,
            Deadline(started_monotonic=0.0, limit_seconds=0.0),
        )

    assert not output.exists()


def test_bundle_cleans_output_when_final_completion_write_exceeds_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "slow-completion"
    bundle = ArtifactBundle({}, {}, {}, "report", {})
    now = [0.0]
    original_write = artifacts._atomic_write

    def monotonic_clock() -> float:
        return now[0]

    def slow_final_write(path: Path, content: bytes) -> None:
        original_write(path, content)
        if path.name == "run-metadata.json":
            now[0] = 2.0

    monkeypatch.setattr("research.financial_jepa.contracts.monotonic", monotonic_clock)
    monkeypatch.setattr(artifacts, "_atomic_write", slow_final_write)

    with pytest.raises(DeadlineExceededError):
        write_bundle(
            REPO_ROOT,
            output,
            bundle,
            Deadline(started_monotonic=0.0, limit_seconds=1.0),
        )

    assert not output.exists()


def test_cli_help_has_only_operational_flags() -> None:
    completed = _run("--help")

    assert completed.returncode == 0, completed.stderr
    assert "--data-dir" in completed.stdout
    assert "--offline" in completed.stdout
    assert "--output-dir" in completed.stdout
    assert "--epochs" not in completed.stdout
    assert "--seed" not in completed.stdout


def test_cli_offline_invalid_cache_fails_without_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    completed = _run(
        "--offline",
        "--data-dir",
        str(tmp_path / "missing-cache"),
        "--output-dir",
        str(output),
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_synthetic_end_to_end_emits_all_frozen_fits(tmp_path: Path) -> None:
    from datetime import date, timedelta

    config = ExperimentConfig.synthetic(context_length=3, future_length=2, batch_size=2, epochs=1)
    rows: list[YieldRow] = []
    for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0)):
        rows.extend(
            YieldRow(
                date(year, 1, 1) + timedelta(days=index),
                curve(base + 0.03 * index, 0.05),
                False,
            )
            for index in range(22)
        )
    prepared = prepare_splits(tuple(rows), config)
    output = tmp_path / "synthetic-run"

    run_prepared_experiment(
        ExperimentRequest(
            repo_root=REPO_ROOT,
            output_dir=output,
            config=config,
            prepared=prepared,
            source_metadata={"fixture": "generated_synthetic_test_only"},
            deadline=Deadline.start(60.0),
        )
    )

    results = json.loads((output / "results.json").read_text())
    assert len(results["fits"]) == 9
    assert {fit["variant"] for fit in results["fits"]} == {
        "regularized",
        "no_regularizer",
        "shuffled_target",
    }
    assert results["verdict"] in {"preliminary_descriptive_signal", "negative_or_inconclusive"}
    assert "winning_run" not in results
    date_hashes = {fit["date_sha256"] for fit in results["fits"]}
    assert date_hashes == {results["raw_baselines"]["date_sha256"]}
    assert all(
        set(fit["diagnostics"]) == {"train", "validation", "test"} for fit in results["fits"]
    )
    assert all(
        fit["readout_identity"]["shared_alpha"] == fit["ridge_alpha"]
        and set(fit["readout_identity"])
        == {
            "shared_alpha",
            "coefficients_sha256",
            "feature_scalers_sha256",
            "intercepts_sha256",
            "combined_sha256",
        }
        for fit in results["fits"]
    )
    assert set(results["raw_baselines"]["direct_ridge"]["model_identity"]) == {
        "alpha",
        "coefficients_sha256",
        "feature_scaler_sha256",
        "intercept_sha256",
        "combined_sha256",
    }
    metadata = json.loads((output / "run-metadata.json").read_text())
    assert metadata["numpy_version"] == np.__version__
    assert {"uv.lock", "scripts/run_financial_jepa.py"}.issubset(metadata["code_identity"]["files"])
    expected_code_files = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "src/research/financial_jepa").glob("*.py")
    } | {"uv.lock", "scripts/run_financial_jepa.py"}
    assert set(metadata["code_identity"]["files"]) == expected_code_files
    assert metadata["frozen_protocol_identity"] == {
        "protocol_version": "yield-jepa/1",
        "protocol_sha256": metadata["protocol_sha256"],
    }
    assert "elapsed_seconds" not in metadata
    assert metadata["computation_preparation_elapsed_seconds"] >= 0.0
    report = (output / "report.md").read_text()
    assert "## Raw Baselines" in report
    assert "## Per-seed JEPA Results" in report
    assert "## Aggregate RMSE" in report
    assert "## Collapse Diagnostics" in report
    assert "## Failed Predeclared Conditions" in report
    assert "## Limitations" in report
    assert f"{results['raw_baselines']['direct_ridge']['overall_rmse_bp']:.6f}" in report


def test_expired_experiment_deadline_creates_no_output(tmp_path: Path) -> None:
    from datetime import date, timedelta

    config = ExperimentConfig.synthetic(context_length=2, future_length=1, batch_size=2, epochs=1)
    output = tmp_path / "expired"
    rows = tuple(
        YieldRow(
            date(year, 1, 1) + timedelta(days=index),
            curve(base + index, 1.0),
            False,
        )
        for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0))
        for index in range(6)
    )
    prepared = prepare_splits(rows, config)

    with pytest.raises(DeadlineExceededError):
        run_prepared_experiment(
            ExperimentRequest(
                repo_root=REPO_ROOT,
                output_dir=output,
                config=config,
                prepared=prepared,
                source_metadata={},
                deadline=Deadline(started_monotonic=0.0, limit_seconds=0.0),
            )
        )

    assert not output.exists()
