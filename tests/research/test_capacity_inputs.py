from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from research.financial_jepa.capacity_inputs import (
    CapacityInput,
    feature_pairs,
    model_features,
    validate_membership,
    validate_selection_protocol,
)
from research.financial_jepa.contracts import ProtocolError, YieldRow
from research.financial_jepa.dataset import prepare_development
from research.financial_jepa.diagnostic_artifacts import LoadedDiagnosticBundle
from research.financial_jepa.diagnostic_contracts import DiagnosticConfig
from research.financial_jepa.diagnostic_reporting import diagnostic_protocol
from research.financial_jepa.model import build_model
from tests.research.support import curve


@pytest.fixture
def source() -> CapacityInput:
    config = DiagnosticConfig()
    rows = tuple(
        YieldRow(
            date(year, 1, 1) + timedelta(days=index),
            curve(1 + index * 0.01, 0.1 + index * 0.001),
            False,
        )
        for year in (2017, 2018)
        for index in range(50)
    )
    prepared = prepare_development(rows, config.training_config())
    validation = {
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
    model = build_model(config.training_config(), 17)
    states = {
        f"seed_17.{label}.{key}": value.numpy().copy()
        for label in ("initial", "selected")
        for key, value in model.state_dict().items()
    }
    bundle = LoadedDiagnosticBundle(
        diagnostic_protocol(config),
        {},
        {"status": "development_selection"},
        states,
        {"dataset_scaler.mean": prepared.scaler.mean, "dataset_scaler.std": prepared.scaler.std},
        validation,
    )
    return CapacityInput(bundle, prepared, {})


def test_budget_groups_use_same_inputs_targets_and_seed(source: CapacityInput) -> None:
    validate_selection_protocol(source.bundle)
    validate_membership(source.bundle, source.prepared)
    pairs = feature_pairs(source, 17)
    assert len(pairs) == 6
    assert all(np.array_equal(pairs[0].train_targets, pair.train_targets) for pair in pairs)
    assert all(np.array_equal(pairs[0].selection_targets, pair.selection_targets) for pair in pairs)
    assert all(pair.seed == 17 for pair in pairs)
    with pytest.raises(ProtocolError, match="seed"):
        feature_pairs(source, 99)


def test_current_group_sees_only_last_curve(source: CapacityInput) -> None:
    original = source.prepared.validation
    modified = replace(
        original,
        windows=tuple(
            replace(window, context=np.concatenate((window.context[:-1] + 20, window.context[-1:])))
            for window in original.windows
        ),
    )
    current, predicted = model_features(source, 17, "initial", original)
    changed_current, changed_predicted = model_features(source, 17, "initial", modified)
    assert np.array_equal(current, changed_current)
    assert not np.array_equal(predicted, changed_predicted)
    with pytest.raises(ProtocolError, match="missing"):
        model_features(source, 43, "initial", original)


@pytest.mark.parametrize("mutation", ["date", "target", "schema", "scaler", "future", "selection"])
def test_source_mismatches_are_refused(source: CapacityInput, mutation: str) -> None:
    bundle, prepared = source.bundle, source.prepared
    match mutation:
        case "date":
            bundle.validation["origin_dates"] = np.asarray(["2018-02-01"])
        case "target":
            bundle.validation["raw_actual_future"] = (
                bundle.validation["raw_actual_future"].astype(np.float64) + 1
            )
        case "schema":
            bundle.validation["raw_contexts"] = np.zeros((1, 1))
        case "scaler":
            bundle.ridge["dataset_scaler.mean"] = prepared.scaler.mean + 1
        case "future":
            first = prepared.validation.windows[0]
            bad = replace(first, target_dates=(date(2022, 1, 1), *first.target_dates[1:]))
            prepared = replace(
                prepared,
                validation=replace(
                    prepared.validation, windows=(bad, *prepared.validation.windows[1:])
                ),
            )
        case "selection":
            bundle.results["status"] = "heldout"
    with pytest.raises(ProtocolError):
        validate_selection_protocol(bundle)
        validate_membership(bundle, prepared)
