from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from research.financial_jepa.capacity_fitting import project_training, run_trial
from research.financial_jepa.capacity_models import FeaturePair
from research.financial_jepa.capacity_storage import load_bundle, write_bundle
from research.financial_jepa.contracts import ProtocolError
from research.financial_jepa.walkforward_protocol import preregister_folds


def pair() -> FeaturePair:
    rng = np.random.default_rng(17)
    return FeaturePair(
        name="raw_current",
        group="current",
        seed=17,
        input_budget=8,
        train=rng.normal(size=(50, 8)),
        selection=rng.normal(size=(12, 8)),
        train_targets=rng.normal(size=(50, 5, 8)),
        selection_targets=rng.normal(size=(12, 5, 8)),
    )


def test_projection_fits_training_only_and_readout_dimensions_are_checked() -> None:
    original = pair()
    projected, evaluated, state = project_training(original.train, original.selection, 4)
    changed, shifted, same_state = project_training(original.train, original.selection + 100, 4)
    assert np.array_equal(projected, changed)
    assert not np.array_equal(evaluated, shifted)
    assert all(np.array_equal(state[key], same_state[key]) for key in state)
    with pytest.raises(ProtocolError, match="budget"):
        run_trial(replace(original, input_budget=240))


def test_matched_readout_records_exact_parameter_budget_and_failure() -> None:
    trial, arrays = run_trial(pair())
    assert trial.status == "ok"
    assert trial.readout_features == 8 and trial.readout_parameters == 360
    assert trial.selected_alpha in (0.0001, 0.01, 1.0, 100.0)
    assert arrays["forecast"].shape == (12, 5, 8)
    original = pair()
    failed, _ = run_trial(replace(original, train=np.full_like(original.train, np.nan)))
    assert failed.status == "failed" and failed.error


def test_bundle_roundtrip_rejects_tamper_and_existing_destination(tmp_path: Path) -> None:
    path = tmp_path / "run"
    write_bundle(path, {"selection": "development_selection"}, {"values": np.arange(4.0)})
    assert load_bundle(path).document["selection"] == "development_selection"
    with pytest.raises(FileExistsError):
        write_bundle(path, {}, {"values": np.arange(4.0)})
    (path / "document.json").write_text("{}")
    with pytest.raises(ProtocolError, match="hash"):
        load_bundle(path)


def test_walkforward_is_preregistered_and_reserved_dates_are_refused() -> None:
    dates = tuple(
        date(year, 1, 1) + timedelta(days=index) for year in range(2001, 2022) for index in range(5)
    )
    protocol = preregister_folds(dates, "a" * 64)
    assert protocol.reserved_period == ("2022-01-01", "2025-12-31")
    assert protocol.status == "preregistered_not_executed"
    assert len(protocol.folds) == 4
    for fold in protocol.folds:
        assert max(fold.training_dates) < min(fold.selection_dates)
        assert max(fold.selection_dates) < min(fold.diagnostic_dates)
        assert len(fold.membership_sha256) == 64
    with pytest.raises(ProtocolError, match="reserved"):
        preregister_folds((*dates, date(2022, 1, 1)), "a" * 64)
