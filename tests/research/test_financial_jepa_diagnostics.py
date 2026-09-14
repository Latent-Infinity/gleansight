from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from research.financial_jepa.contracts import (
    Deadline,
    DevelopmentData,
    ExperimentConfig,
    JsonValue,
    ProtocolError,
    Variant,
    YieldRow,
)
from research.financial_jepa.dataset import prepare_development
from research.financial_jepa.diagnostic_artifacts import (
    DiagnosticBundle,
    _json_bytes,
    _npz_bytes,
    load_diagnostic_bundle,
    write_diagnostic_bundle,
)
from research.financial_jepa.diagnostic_contracts import DiagnosticConfig
from research.financial_jepa.diagnostic_probes import representation_summary
from research.financial_jepa.diagnostic_reload import reload_and_verify
from research.financial_jepa.diagnostic_validation import validate_date_arrays
from research.financial_jepa.diagnostic_workflow import (
    PreparedDiagnosticRequest,
    run_prepared_diagnostics,
)
from research.financial_jepa.provenance import rights_metadata
from research.financial_jepa.treasury import (
    AcquisitionRequest,
    CacheMetadata,
    acquire_years,
)
from tests.research.support import curve

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/diagnose_financial_jepa.py"


def _config() -> DiagnosticConfig:
    return DiagnosticConfig(
        label="synthetic_test_only",
        context_length=3,
        future_length=2,
        batch_size=2,
        epochs=1,
        seeds=(17,),
        deadline_seconds=60.0,
    )


def _rows() -> tuple[YieldRow, ...]:
    return tuple(
        YieldRow(
            date(year, 1, 1) + timedelta(days=index),
            curve(base + 0.03 * index, 0.05 + 0.001 * index),
            False,
        )
        for year, base in ((2017, 1.0), (2018, 2.0))
        for index in range(22)
    )


def _source() -> dict[str, JsonValue]:
    source = rights_metadata()
    source["yearly_responses"] = []
    source["dropped_missing_dates"] = []
    source["missing_tenor_rows"] = []
    return source


def _run_bundle(tmp_path: Path) -> Path:
    config = _config()
    prepared = prepare_development(_rows(), config.training_config())
    return run_prepared_diagnostics(
        PreparedDiagnosticRequest(
            REPO_ROOT,
            tmp_path / "diagnostics",
            config,
            prepared,
            _source(),
            Deadline.start(60.0),
        )
    )


def _rehash(run_root: Path, filename: str) -> None:
    metadata_path = run_root / "run-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["artifact_sha256"][filename] = hashlib.sha256(
        (run_root / filename).read_bytes()
    ).hexdigest()
    metadata_path.write_text(json.dumps(metadata))


def test_synthetic_bundle_reloads_exact_forecasts_states_ridges_and_metrics(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)

    verified = reload_and_verify(run_root)

    assert {path.name for path in run_root.iterdir()} == {
        "protocol.json",
        "source-metadata.json",
        "results.json",
        "states.npz",
        "ridge.npz",
        "validation.npz",
        "report.md",
        "run-metadata.json",
    }
    assert set(verified.forecasts) == {
        "persistence",
        "raw_history",
        "seed_17.selected_ema_current",
        "seed_17.predicted_future",
        "seed_17.frozen_random_current",
    }
    assert all(np.isfinite(values).all() for values in verified.forecasts.values())
    assert verified.bundle.results["status"] == "synthetic_test_only"
    assert all(not values.dtype.hasobject for values in verified.bundle.states.values())
    assert all(not values.dtype.hasobject for values in verified.bundle.ridge.values())
    assert all(not values.dtype.hasobject for values in verified.bundle.validation.values())


def test_loader_rejects_tampered_bytes_before_parsing(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    states = run_root / "states.npz"
    states.write_bytes(states.read_bytes() + b"tampered")

    with pytest.raises(ProtocolError, match="hash mismatch"):
        load_diagnostic_bundle(run_root)


def test_loader_rejects_unknown_npz_key_even_with_updated_hash(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    ridge_path = run_root / "ridge.npz"
    with np.load(ridge_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["unknown"] = np.asarray([1.0])
    np.savez(ridge_path, **arrays)
    _rehash(run_root, "ridge.npz")

    with pytest.raises(ProtocolError, match="unknown or missing keys"):
        load_diagnostic_bundle(run_root)


def test_loader_rejects_pickle_object_array_even_with_updated_manifests(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    results_path = run_root / "results.json"
    results = json.loads(results_path.read_text())
    results["array_manifest"]["ridge.npz"]["bad"] = {"shape": [1], "dtype": "|O"}
    results_path.write_text(json.dumps(results))
    ridge_path = run_root / "ridge.npz"
    with np.load(ridge_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["bad"] = np.asarray([{"unsafe": True}], dtype=object)
    np.savez(ridge_path, **arrays)
    _rehash(run_root, "ridge.npz")
    _rehash(run_root, "results.json")

    with pytest.raises(ProtocolError, match="pickle"):
        load_diagnostic_bundle(run_root)


def test_default_config_and_cli_are_development_only_and_operational() -> None:
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "UV_NO_SYNC": "1"}
    completed = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/python"), str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert DiagnosticConfig().years == tuple(range(2001, 2022))
    assert "--data-dir" in completed.stdout
    assert "--offline" in completed.stdout
    assert "--no-offline" in completed.stdout
    assert "--output-dir" in completed.stdout
    assert "--epochs" not in completed.stdout
    assert "--seed" not in completed.stdout


def test_cli_default_offline_bad_cache_writes_nothing(tmp_path: Path) -> None:
    data_dir = tmp_path / "missing-cache"
    output_dir = tmp_path / "output"
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "UV_NO_SYNC": "1"}

    completed = subprocess.run(
        [
            str(REPO_ROOT / ".venv/bin/python"),
            str(SCRIPT),
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert not data_dir.exists()
    assert not output_dir.exists()


def test_diagnostic_acquisition_names_only_2001_through_2021(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested: list[int] = []

    def cached(data_dir: Path, year: int) -> tuple[Path, CacheMetadata]:
        if year >= 2022:
            raise AssertionError("held-out cache access")
        requested.append(year)
        return data_dir / f"{year}.xml", CacheMetadata(
            year=year,
            url=f"https://example.invalid/{year}",
            retrieved_at_utc="2026-09-13T00:00:00Z",
            status_code=200,
            content_type="application/xml",
            etag=None,
            last_modified=None,
            sha256="0" * 64,
            byte_count=0,
        )

    monkeypatch.setattr("research.financial_jepa.treasury._verified_cached", cached)

    acquire_years(
        AcquisitionRequest(
            DiagnosticConfig().training_config(),
            tmp_path,
            True,
            Deadline.start(60.0),
        )
    )

    assert requested == list(range(2001, 2022))


def test_runtime_guard_rejects_manually_injected_heldout_window_before_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config()
    prepared = prepare_development(_rows(), config.training_config())
    first = prepared.validation.windows[0]
    invalid = replace(
        first,
        context_dates=tuple(date(2022, 1, 1) + timedelta(days=i) for i in range(3)),
        target_dates=tuple(date(2022, 1, 4) + timedelta(days=i) for i in range(2)),
    )
    invalid_validation = replace(
        prepared.validation,
        windows=(invalid, *prepared.validation.windows[1:]),
    )
    called = False

    def forbidden_train(
        development: DevelopmentData,
        training_config: ExperimentConfig,
        variant: Variant,
        seed: int,
        deadline: Deadline | None,
    ) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "research.financial_jepa.diagnostic_workflow.train_variant_recorded", forbidden_train
    )

    with pytest.raises(ProtocolError, match="validation window"):
        run_prepared_diagnostics(
            PreparedDiagnosticRequest(
                REPO_ROOT,
                tmp_path / "guarded",
                config,
                replace(prepared, validation=invalid_validation),
                _source(),
                Deadline.start(60.0),
            )
        )

    assert called is False


def test_runtime_guard_rejects_nonfrozen_year_configuration(tmp_path: Path) -> None:
    config = _config()
    prepared = prepare_development(_rows(), config.training_config())
    changed = config.model_copy(update={"years": tuple(range(2002, 2022))})

    with pytest.raises(ProtocolError, match="exactly 2001 through 2021"):
        run_prepared_diagnostics(
            PreparedDiagnosticRequest(
                REPO_ROOT,
                tmp_path / "guarded",
                changed,
                prepared,
                _source(),
                Deadline.start(60.0),
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context_length", 3),
        ("future_length", 2),
        ("batch_size", 2),
        ("epochs", 1),
        ("seeds", (43, 29, 17)),
        ("ridge_alphas", (1e2, 1.0, 1e-2, 1e-4)),
        ("deadline_seconds", 60.0),
    ],
)
def test_production_label_rejects_every_nonfrozen_field_before_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: int | float | tuple[int, ...] | tuple[float, ...],
) -> None:
    synthetic = _config()
    prepared = prepare_development(_rows(), synthetic.training_config())
    changed = DiagnosticConfig().model_copy(update={field: value})
    called = False

    def forbidden_train(
        development: DevelopmentData,
        training_config: ExperimentConfig,
        variant: Variant,
        seed: int,
        deadline: Deadline | None,
    ) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "research.financial_jepa.diagnostic_workflow.train_variant_recorded", forbidden_train
    )

    with pytest.raises(ProtocolError, match="frozen production configuration"):
        run_prepared_diagnostics(
            PreparedDiagnosticRequest(
                REPO_ROOT, tmp_path / field, changed, prepared, _source(), Deadline.start(900.0)
            )
        )

    assert called is False


def test_unknown_label_copied_into_config_is_rejected_before_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config()
    prepared = prepare_development(_rows(), config.training_config())
    changed = config.model_copy(update={"label": "unexpected"})
    called = False

    def forbidden_train(
        development: DevelopmentData,
        training_config: ExperimentConfig,
        variant: Variant,
        seed: int,
        deadline: Deadline | None,
    ) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "research.financial_jepa.diagnostic_workflow.train_variant_recorded", forbidden_train
    )

    with pytest.raises(ProtocolError, match="invalid diagnostic configuration"):
        run_prepared_diagnostics(
            PreparedDiagnosticRequest(
                REPO_ROOT,
                tmp_path / "unknown-label",
                changed,
                prepared,
                _source(),
                Deadline.start(60.0),
            )
        )

    assert called is False


def test_synthetic_identity_cannot_write_repository_output(tmp_path: Path) -> None:
    config = _config()
    prepared = prepare_development(_rows(), config.training_config())

    with pytest.raises(ProtocolError, match="synthetic diagnostics require temporary output"):
        run_prepared_diagnostics(
            PreparedDiagnosticRequest(
                REPO_ROOT,
                REPO_ROOT / "output/financial-jepa-diagnostics/synthetic-forbidden",
                config,
                prepared,
                _source(),
                Deadline.start(60.0),
            )
        )


def test_prepared_row_metadata_and_scaler_are_rebuilt_before_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config()
    prepared = prepare_development(_rows(), config.training_config())
    injected = replace(
        prepared,
        train_rows=(
            replace(prepared.train_rows[0], observed_on=date(2022, 1, 1)),
            *prepared.train_rows[1:],
        ),
    )
    inconsistent = replace(
        prepared,
        scaler=replace(prepared.scaler, mean=prepared.scaler.mean + 1.0),
    )
    called = False

    def forbidden_train(
        development: DevelopmentData,
        training_config: ExperimentConfig,
        variant: Variant,
        seed: int,
        deadline: Deadline | None,
    ) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "research.financial_jepa.diagnostic_workflow.train_variant_recorded", forbidden_train
    )

    for candidate in (injected, inconsistent):
        with pytest.raises(ProtocolError):
            run_prepared_diagnostics(
                PreparedDiagnosticRequest(
                    REPO_ROOT,
                    tmp_path / f"guard-{candidate.train_rows[0].observed_on.year}",
                    config,
                    candidate,
                    _source(),
                    Deadline.start(60.0),
                )
            )

    assert called is False


def test_results_include_all_seed_aggregate_axes(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    results = json.loads((run_root / "results.json").read_text())

    aggregates = results["aggregates"]
    forecast = aggregates["forecast_methods"]["selected_ema_current"]
    assert set(forecast) == {
        "overall_rmse_bp",
        "per_horizon_rmse_bp",
        "per_tenor_rmse_bp",
        "matrix_rmse_bp",
    }
    assert forecast["overall_rmse_bp"]["population_std"] == 0.0
    assert aggregates["latent"]["predicted_future"]["per_horizon_mse"]["population_std"] == [
        0.0,
        0.0,
    ]
    assert aggregates["current_reconstruction"]["matrix_rmse_bp"]["population_std"] == [[0.0] * 8]
    representation = aggregates["representations"]["train_selected_ema"]
    assert set(representation) == {
        "per_dimension_sample_std",
        "mean_sample_std",
        "covariance_effective_rank",
    }


def test_reload_rejects_hash_valid_seed_aggregate_drift(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    results_path = run_root / "results.json"
    results = json.loads(results_path.read_text())
    aggregate = results["aggregates"]["forecast_methods"]["predicted_future"]
    aggregate["overall_rmse_bp"]["mean"] += 1.0
    results_path.write_text(json.dumps(results))
    _rehash(run_root, "results.json")

    with pytest.raises(ProtocolError, match="aggregate"):
        reload_and_verify(run_root)


def _rewrite_npz(run_root: Path, filename: str, arrays: dict[str, np.ndarray]) -> None:
    path = run_root / filename
    np.savez(path, **arrays)
    _rehash(run_root, filename)


def test_reload_rejects_hash_valid_future_latent_semantic_mutation(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    validation_path = run_root / "validation.npz"
    with np.load(validation_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["latent.seed_17.ema_future"] += 1.0
    predicted_error = (
        arrays["latent.seed_17.predicted_future"] - arrays["latent.seed_17.ema_future"]
    ) ** 2
    persistence_error = (
        arrays["latent.seed_17.ema_current"] - arrays["latent.seed_17.ema_future"]
    ) ** 2
    results_path = run_root / "results.json"
    results = json.loads(results_path.read_text())
    latent = results["seeds"][0]["latent"]
    latent["predicted_future_overall_mse"] = float(predicted_error.mean())
    latent["predicted_future_per_horizon_mse"] = list(predicted_error.mean(axis=(0, 2)))
    latent["ema_current_persistence_overall_mse"] = float(persistence_error.mean())
    latent["ema_current_persistence_per_horizon_mse"] = list(persistence_error.mean(axis=(0, 2)))
    results_path.write_text(json.dumps(results))
    _rewrite_npz(run_root, "validation.npz", arrays)
    _rehash(run_root, "results.json")

    with pytest.raises(ProtocolError, match="semantic latent"):
        reload_and_verify(run_root)


def test_reload_rejects_hash_valid_representation_semantic_mutation(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    validation_path = run_root / "validation.npz"
    with np.load(validation_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    key = "representation.seed_17.train_selected"
    arrays[key] += np.linspace(0.0, 1.0, arrays[key].shape[1])
    per_dimension, summary = representation_summary(arrays[key])
    results_path = run_root / "results.json"
    results = json.loads(results_path.read_text())
    record = results["seeds"][0]["representations"]["train_selected_ema"]
    record["per_dimension_sample_std"] = list(per_dimension)
    record["mean_sample_std"] = summary.mean_sample_std
    record["covariance_effective_rank"] = summary.effective_rank
    results_path.write_text(json.dumps(results))
    _rewrite_npz(run_root, "validation.npz", arrays)
    _rehash(run_root, "results.json")

    with pytest.raises(ProtocolError, match="semantic representation"):
        reload_and_verify(run_root)


def test_reload_rejects_invalid_validation_date_after_hash_and_manifest_update(
    tmp_path: Path,
) -> None:
    run_root = _run_bundle(tmp_path)
    validation_path = run_root / "validation.npz"
    with np.load(validation_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["origin_dates"][0] = "invalid"
    np.savez(validation_path, **arrays)
    _rehash(run_root, "validation.npz")

    with pytest.raises(ProtocolError, match="invalid ISO dates"):
        reload_and_verify(run_root)


def test_reload_rejects_saved_metric_drift(tmp_path: Path) -> None:
    run_root = _run_bundle(tmp_path)
    results_path = run_root / "results.json"
    results = json.loads(results_path.read_text())
    results["methods"]["raw_history"]["overall_rmse_bp"] += 1.0
    results_path.write_text(json.dumps(results))
    _rehash(run_root, "results.json")

    with pytest.raises(ProtocolError, match="saved metrics"):
        reload_and_verify(run_root)


def test_npz_boundary_rejects_empty_and_object_payloads() -> None:
    with pytest.raises(ProtocolError, match="empty"):
        _npz_bytes({})
    with pytest.raises(ProtocolError, match="pickle-free"):
        _npz_bytes({"unsafe": np.asarray([{"value": 1}], dtype=object)})
    with pytest.raises(ProtocolError, match="numeric or fixed Unicode"):
        _npz_bytes({"complex": np.asarray([1.0j])})
    with pytest.raises(ProtocolError, match="invalid JSON"):
        _json_bytes({"nonfinite": float("nan")})


def test_date_array_boundary_rejects_dtype_and_split_year() -> None:
    valid = {
        "train_row_dates": np.asarray(["2017-01-01"], dtype="U10"),
        "validation_row_dates": np.asarray(["2018-01-01"], dtype="U10"),
        "origin_dates": np.asarray(["2018-01-01"], dtype="U10"),
        "target_dates": np.asarray([["2018-01-02"]], dtype="U10"),
    }
    invalid_dtype = {**valid, "origin_dates": np.asarray([b"2018-01-01"], dtype="S10")}
    invalid_year = {**valid, "target_dates": np.asarray([["2022-01-02"]], dtype="U10")}

    with pytest.raises(ProtocolError, match="fixed U10"):
        validate_date_arrays(invalid_dtype)
    with pytest.raises(ProtocolError, match="outside its development split"):
        validate_date_arrays(invalid_year)


def test_expired_diagnostic_bundle_leaves_no_completion_marker(tmp_path: Path) -> None:
    output = tmp_path / "expired"
    bundle = DiagnosticBundle(
        protocol={},
        source_metadata={},
        results={},
        states={"value": np.asarray([1.0])},
        ridge={"value": np.asarray([1.0])},
        validation={"value": np.asarray([1.0])},
        report="",
        run_metadata={},
    )

    with pytest.raises(TimeoutError):
        write_diagnostic_bundle(
            REPO_ROOT,
            output,
            bundle,
            Deadline(started_monotonic=0.0, limit_seconds=0.0),
        )

    assert not output.exists()
