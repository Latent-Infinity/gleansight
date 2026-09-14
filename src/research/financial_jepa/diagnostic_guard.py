from __future__ import annotations

import tempfile
from pathlib import Path
from typing import assert_never

import numpy as np
from pydantic import ValidationError

from research.financial_jepa.contracts import ExperimentConfig, ProtocolError, WindowSet
from research.financial_jepa.dataset import prepare_development
from research.financial_jepa.diagnostic_contracts import (
    DiagnosticConfig,
    PreparedDevelopment,
)


def _same_windows(actual: WindowSet, expected: WindowSet) -> bool:
    if (
        actual.segment_count != expected.segment_count
        or actual.discarded_window_count != expected.discarded_window_count
        or actual.gap_histogram != expected.gap_histogram
        or not np.array_equal(actual.unique_rows, expected.unique_rows)
        or len(actual.windows) != len(expected.windows)
    ):
        return False
    return all(
        observed.context_dates == rebuilt.context_dates
        and observed.target_dates == rebuilt.target_dates
        and observed.origin_date == rebuilt.origin_date
        and np.array_equal(observed.context, rebuilt.context)
        and np.array_equal(observed.future, rebuilt.future)
        and np.array_equal(observed.raw_context, rebuilt.raw_context)
        and np.array_equal(observed.raw_future, rebuilt.raw_future)
        for observed, rebuilt in zip(actual.windows, expected.windows, strict=True)
    )


def _validate_config(config: DiagnosticConfig, output_dir: Path | None) -> None:
    try:
        validated = DiagnosticConfig.model_validate(config.model_dump(), strict=True)
    except ValidationError as exc:
        raise ProtocolError("invalid diagnostic configuration") from exc
    match validated.label:
        case "development_selection":
            if validated != DiagnosticConfig():
                raise ProtocolError("diagnostic requires the frozen production configuration")
        case "synthetic_test_only":
            if validated.years != tuple(range(2001, 2022)):
                raise ProtocolError("diagnostic years must be exactly 2001 through 2021")
            temporary = Path(tempfile.gettempdir()).resolve()
            if output_dir is None or not output_dir.resolve().is_relative_to(temporary):
                raise ProtocolError("synthetic diagnostics require temporary output")
        case unreachable:
            assert_never(unreachable)


def _validate_window_years(prepared: PreparedDevelopment) -> None:
    for window in prepared.train.windows:
        if any(
            day.year < 2001 or day.year > 2017
            for day in (*window.context_dates, *window.target_dates)
        ):
            raise ProtocolError("training window is outside 2001 through 2017")
    for window in prepared.validation.windows:
        if any(
            day.year < 2018 or day.year > 2021
            for day in (*window.context_dates, *window.target_dates)
        ):
            raise ProtocolError("validation window is outside 2018 through 2021")


def validate_diagnostic_request(
    config: DiagnosticConfig,
    prepared: PreparedDevelopment,
    output_dir: Path | None,
    deadline_seconds: float,
) -> None:
    _validate_config(config, output_dir)
    _validate_window_years(prepared)
    if deadline_seconds != config.deadline_seconds:
        raise ProtocolError("diagnostic deadline disagrees with configuration")
    training_config: ExperimentConfig = config.training_config()
    rebuilt = prepare_development(
        (*prepared.train_rows, *prepared.validation_rows), training_config
    )
    if (
        prepared.train_rows != rebuilt.train_rows
        or prepared.validation_rows != rebuilt.validation_rows
        or not np.array_equal(prepared.scaler.mean, rebuilt.scaler.mean)
        or not np.array_equal(prepared.scaler.std, rebuilt.scaler.std)
        or not _same_windows(prepared.train, rebuilt.train)
        or not _same_windows(prepared.validation, rebuilt.validation)
    ):
        raise ProtocolError("prepared development data does not match its dated raw rows")
