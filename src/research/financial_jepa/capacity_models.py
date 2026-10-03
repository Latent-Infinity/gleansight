from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from research.financial_jepa.contracts import FloatArray

type CapacityGroup = Literal["current", "history"]


@dataclass(frozen=True, slots=True)
class FeaturePair:
    name: str
    group: CapacityGroup
    seed: int
    input_budget: int
    train: FloatArray
    selection: FloatArray
    train_targets: FloatArray
    selection_targets: FloatArray


class Trial(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    method: str
    group: CapacityGroup
    seed: int
    status: Literal["ok", "failed"]
    input_budget: int
    readout_features: int
    readout_parameters: int
    train_rows: int
    selection_rows: int
    selected_alpha: float | None = None
    rmse_bp: float | None = None
    per_horizon_rmse_bp: tuple[float, ...] = ()
    training_feature_rank: int | None = None
    projection_variance_retained: float | None = None
    error: str | None = None
