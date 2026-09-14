from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import torch
from pydantic import BaseModel, ConfigDict

from research.financial_jepa.contracts import (
    ALPHAS,
    SEEDS,
    ExperimentConfig,
    Scaler,
    TrainResult,
    Variant,
    WindowSet,
    YieldRow,
)

DIAGNOSTIC_PROTOCOL_VERSION: Final = "yield-jepa-diagnostics/1"
DEVELOPMENT_YEARS: Final = tuple(range(2001, 2022))


type DiagnosticLabel = Literal["development_selection", "synthetic_test_only"]


class DiagnosticConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: DiagnosticLabel = "development_selection"
    years: tuple[int, ...] = DEVELOPMENT_YEARS
    context_length: int = 30
    future_length: int = 5
    batch_size: int = 128
    epochs: int = 10
    seeds: tuple[int, ...] = SEEDS
    ridge_alphas: tuple[float, ...] = ALPHAS
    deadline_seconds: float = 900.0

    def training_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            label=self.label,
            years=self.years,
            context_length=self.context_length,
            future_length=self.future_length,
            batch_size=self.batch_size,
            epochs=self.epochs,
            variants=(Variant.REGULARIZED,),
            seeds=self.seeds,
            ridge_alphas=self.ridge_alphas,
            deadline_seconds=self.deadline_seconds,
        )


@dataclass(frozen=True, slots=True)
class PreparedDevelopment:
    train: WindowSet
    validation: WindowSet
    scaler: Scaler
    train_rows: tuple[YieldRow, ...]
    validation_rows: tuple[YieldRow, ...]


@dataclass(frozen=True, slots=True)
class EpochRecord:
    epoch: int
    batch_count: int
    window_count: int
    mean_prediction_loss: float
    mean_variance_loss: float
    mean_covariance_loss: float
    mean_total_loss: float
    aligned_validation_mse: float
    checkpoint_updated: bool


@dataclass(frozen=True, slots=True)
class RecordedTrainResult:
    result: TrainResult
    initial_model_state: dict[str, torch.Tensor]
    epochs: tuple[EpochRecord, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticRequest:
    repo_root: Path
    data_dir: Path
    output_dir: Path | None
    offline: bool
