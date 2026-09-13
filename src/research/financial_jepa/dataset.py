from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

import numpy as np

from research.financial_jepa.contracts import (
    METHODOLOGY_CHANGE,
    ExperimentConfig,
    FloatArray,
    PreparedSplits,
    ProtocolError,
    Scaler,
    Window,
    WindowSet,
    YieldRow,
)


@dataclass(frozen=True, slots=True)
class _Partition:
    name: str
    accepts: Callable[[date], bool]


def _partitions() -> tuple[_Partition, ...]:
    return (
        _Partition("train", lambda observed: 2001 <= observed.year <= 2017),
        _Partition("validation", lambda observed: 2018 <= observed.year <= 2021),
        _Partition("test", lambda observed: 2022 <= observed.year <= 2025),
    )


def _as_array(rows: tuple[YieldRow, ...]) -> FloatArray:
    return np.asarray([row.yields for row in rows], dtype=np.float64)


def _fit_scaler(rows: tuple[YieldRow, ...]) -> Scaler:
    values = _as_array(rows)
    mean = values.mean(axis=0)
    std = values.std(axis=0, ddof=0)
    if not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std == 0.0):
        raise ProtocolError("training scaler has nonfinite values or zero standard deviation")
    return Scaler(mean=mean, std=std)


def _segments(rows: tuple[YieldRow, ...]) -> tuple[tuple[YieldRow, ...], ...]:
    segments: list[list[YieldRow]] = []
    current: list[YieldRow] = []
    previous: YieldRow | None = None
    for row in rows:
        gap_boundary = previous is not None and (row.observed_on - previous.observed_on).days > 4
        methodology_boundary = (
            previous is not None and previous.observed_on < METHODOLOGY_CHANGE <= row.observed_on
        )
        if current and (row.boundary_before or gap_boundary or methodology_boundary):
            segments.append(current)
            current = []
        current.append(row)
        previous = row
    if current:
        segments.append(current)
    return tuple(tuple(segment) for segment in segments)


def _window_set(
    rows: tuple[YieldRow, ...],
    scaler: Scaler,
    config: ExperimentConfig,
) -> WindowSet:
    segments = _segments(rows)
    windows: list[Window] = []
    width = config.context_length + config.future_length
    candidate_count = max(0, len(rows) - width + 1)
    for segment in segments:
        raw = _as_array(segment)
        scaled = (raw - scaler.mean) / scaler.std
        for start in range(max(0, len(segment) - width + 1)):
            context_end = start + config.context_length
            target_end = context_end + config.future_length
            context_rows = segment[start:context_end]
            target_rows = segment[context_end:target_end]
            windows.append(
                Window(
                    context=scaled[start:context_end].copy(),
                    future=scaled[context_end:target_end].copy(),
                    raw_context=raw[start:context_end].copy(),
                    raw_future=raw[context_end:target_end].copy(),
                    context_dates=tuple(row.observed_on for row in context_rows),
                    target_dates=tuple(row.observed_on for row in target_rows),
                    origin_date=context_rows[-1].observed_on,
                )
            )
    if not windows:
        raise ProtocolError("split has no complete within-segment windows")
    gap_counts = Counter(
        (current.observed_on - previous.observed_on).days for previous, current in pairwise(rows)
    )
    return WindowSet(
        windows=tuple(windows),
        unique_rows=_as_array(rows),
        segment_count=len(segments),
        discarded_window_count=candidate_count - len(windows),
        gap_histogram=tuple(sorted(gap_counts.items())),
    )


def prepare_splits(rows: tuple[YieldRow, ...], config: ExperimentConfig) -> PreparedSplits:
    if not rows:
        raise ProtocolError("yield dataset is empty")
    ordered = tuple(sorted(rows, key=lambda row: row.observed_on))
    dates = tuple(row.observed_on for row in ordered)
    if len(dates) != len(set(dates)):
        raise ProtocolError("yield dataset contains duplicate dates")
    if any(not np.isfinite(row.yields).all() for row in ordered):
        raise ProtocolError("yield dataset contains nonfinite values")
    partitioned = {
        partition.name: tuple(row for row in ordered if partition.accepts(row.observed_on))
        for partition in _partitions()
    }
    if any(not split_rows for split_rows in partitioned.values()):
        raise ProtocolError("yield dataset contains an empty chronological split")
    train_rows = partitioned["train"]
    validation_rows = partitioned["validation"]
    test_rows = partitioned["test"]
    scaler = _fit_scaler(train_rows)
    return PreparedSplits(
        train=_window_set(train_rows, scaler, config),
        validation=_window_set(validation_rows, scaler, config),
        test=_window_set(test_rows, scaler, config),
        scaler=scaler,
    )
