from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Final, Self

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

TENOR_FIELDS: Final = (
    "BC_3MONTH",
    "BC_6MONTH",
    "BC_1YEAR",
    "BC_2YEAR",
    "BC_3YEAR",
    "BC_5YEAR",
    "BC_7YEAR",
    "BC_10YEAR",
)
METHODOLOGY_CHANGE: Final = date(2021, 12, 6)
ALPHAS: Final = (1e-4, 1e-2, 1.0, 1e2)
SEEDS: Final = (17, 29, 43)

type FloatArray = NDArray[np.float64]
type YieldVector = tuple[float, float, float, float, float, float, float, float]
type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class ProtocolError(ValueError):
    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return self.reason


class DeadlineExceededError(TimeoutError):
    __slots__ = ("elapsed_seconds", "limit_seconds")

    def __init__(self, elapsed_seconds: float, limit_seconds: float) -> None:
        super().__init__(elapsed_seconds, limit_seconds)
        self.elapsed_seconds = elapsed_seconds
        self.limit_seconds = limit_seconds

    def __str__(self) -> str:
        return (
            "financial JEPA deadline exceeded "
            f"({self.elapsed_seconds:.3f}s > {self.limit_seconds:.3f}s)"
        )


@dataclass(frozen=True, slots=True)
class Deadline:
    started_monotonic: float
    limit_seconds: float

    @classmethod
    def start(cls, limit_seconds: float = 900.0) -> Self:
        return cls(monotonic(), limit_seconds)

    def check(self, now_monotonic: float | None = None) -> None:
        now = monotonic() if now_monotonic is None else now_monotonic
        elapsed = now - self.started_monotonic
        if elapsed > self.limit_seconds:
            raise DeadlineExceededError(elapsed, self.limit_seconds)

    def elapsed(self, now_monotonic: float | None = None) -> float:
        now = monotonic() if now_monotonic is None else now_monotonic
        return now - self.started_monotonic


class Variant(StrEnum):
    REGULARIZED = "regularized"
    NO_REGULARIZER = "no_regularizer"
    SHUFFLED_TARGET = "shuffled_target"


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    years: tuple[int, ...]
    context_length: int
    future_length: int
    batch_size: int
    epochs: int
    variants: tuple[Variant, ...]
    seeds: tuple[int, ...]
    ridge_alphas: tuple[float, ...]
    deadline_seconds: float

    @classmethod
    def canonical(cls) -> Self:
        return cls(
            label="canonical",
            years=tuple(range(2001, 2026)),
            context_length=30,
            future_length=5,
            batch_size=128,
            epochs=10,
            variants=tuple(Variant),
            seeds=SEEDS,
            ridge_alphas=ALPHAS,
            deadline_seconds=900.0,
        )

    @classmethod
    def synthetic(
        cls,
        *,
        context_length: int,
        future_length: int,
        batch_size: int,
        epochs: int,
    ) -> Self:
        return cls(
            label="synthetic_test_only",
            years=(2017, 2018, 2022),
            context_length=context_length,
            future_length=future_length,
            batch_size=batch_size,
            epochs=epochs,
            variants=tuple(Variant),
            seeds=SEEDS,
            ridge_alphas=ALPHAS,
            deadline_seconds=30.0,
        )

    def validate_paths(self, repo_root: Path, data_dir: Path, output_dir: Path) -> None:
        repository = repo_root.resolve()
        source = data_dir.resolve()
        output = output_dir.resolve()
        permitted_source = repository / "data/research/financial-jepa/treasury"
        permitted_output = repository / "output/financial-jepa"
        temporary = Path("/tmp").resolve()
        if source != permitted_source and not source.is_relative_to(temporary):
            raise ProtocolError("data directory must be the isolated research cache or temporary")
        if not output.is_relative_to(permitted_output) and not output.is_relative_to(temporary):
            raise ProtocolError("output directory must be below output/financial-jepa or temporary")


@dataclass(frozen=True, slots=True)
class YieldRow:
    observed_on: date
    yields: YieldVector
    boundary_before: bool


@dataclass(frozen=True, slots=True)
class ParsedYieldRows:
    rows: tuple[YieldRow, ...]
    dropped_missing_dates: tuple[date, ...]
    missing_fields_by_date: tuple[tuple[date, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class Scaler:
    mean: FloatArray
    std: FloatArray


@dataclass(frozen=True, slots=True)
class Window:
    context: FloatArray
    future: FloatArray
    raw_context: FloatArray
    raw_future: FloatArray
    context_dates: tuple[date, ...]
    target_dates: tuple[date, ...]
    origin_date: date


@dataclass(frozen=True, slots=True)
class WindowSet:
    windows: tuple[Window, ...]
    unique_rows: FloatArray
    segment_count: int
    discarded_window_count: int
    gap_histogram: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class PreparedSplits:
    train: WindowSet
    validation: WindowSet
    test: WindowSet
    scaler: Scaler


@dataclass(frozen=True, slots=True)
class DevelopmentData:
    train: WindowSet
    validation: WindowSet


@dataclass(frozen=True, slots=True)
class TrainResult:
    variant: Variant
    seed: int
    selected_epoch: int
    validation_mse: float
    model_state: dict[str, torch.Tensor]
    state_sha256: str


@dataclass(frozen=True, slots=True)
class RidgeData:
    features: FloatArray
    targets: FloatArray


@dataclass(frozen=True, slots=True)
class RidgeModel:
    alpha: float
    feature_mean: FloatArray
    feature_std: FloatArray
    coefficients: FloatArray
    intercept: FloatArray


@dataclass(frozen=True, slots=True)
class MetricSummary:
    overall_rmse_bp: float
    per_horizon_rmse_bp: tuple[float, ...]
    per_tenor_rmse_bp: tuple[float, ...]
    matrix_rmse_bp: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class CollapseDiagnostics:
    mean_sample_std: float
    effective_rank: float
    collapsed: bool
