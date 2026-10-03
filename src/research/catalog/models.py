from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CatalogError(ValueError):
    __slots__ = ("reason",)
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class MetricDefinition(Contract):
    unit: Literal["basis_points"] = "basis_points"
    formula: Literal["100 * sqrt(mean((predicted_yield_percent - actual_yield_percent)^2))"] = (
        "100 * sqrt(mean((predicted_yield_percent - actual_yield_percent)^2))"
    )
    axes: tuple[Text, ...] = ("paired_origin_date", "future_observation", "tenor")
    tenor_fields: tuple[Text, ...]
    task: Literal["forecast", "reconstruction"] = "forecast"


Nonnegative = Annotated[float, Field(ge=0)]


class MetricValues(Contract):
    overall_rmse_bp: float = Field(ge=0)
    per_horizon_rmse_bp: tuple[Nonnegative, ...]
    per_tenor_rmse_bp: tuple[Nonnegative, ...]
    matrix_rmse_bp: tuple[tuple[Nonnegative, ...], ...]

    @model_validator(mode="after")
    def matching_dimensions(self) -> Self:
        if not self.per_horizon_rmse_bp or not self.per_tenor_rmse_bp:
            raise ValueError("RMSE axes must be nonempty")
        if len(self.matrix_rmse_bp) != len(self.per_horizon_rmse_bp) or any(
            len(row) != len(self.per_tenor_rmse_bp) for row in self.matrix_rmse_bp
        ):
            raise ValueError("RMSE matrix dimensions must match horizon and tenor axes")
        return self


class RunMetric(Contract):
    method: Text
    seed: int | None
    definition: MetricDefinition
    values: MetricValues | None
    artifact_identity: dict[str, JsonValue]
    problem: str | None = None


class VerifiedRun(Contract):
    run_id: Digest
    declared_run_id: Text
    workflow: Literal["financial-jepa", "financial-jepa-diagnostics", "financial-jepa-capacity"]
    classification: Literal["smoke", "development_diagnostic", "evaluation_record"]
    verification: Literal["artifact_hashes", "reconstructed_forecasts", "reconstructed_capacity"]
    source_sha256: Digest
    protocol_sha256: Digest
    split_sha256: Digest
    code_sha256: Digest
    metadata_sha256: Digest
    artifact_sha256: dict[Text, Digest]
    code_files: dict[Text, Digest]
    seeds: tuple[int, ...]
    origin_dates: tuple[date, ...]
    target_dates: tuple[tuple[date, ...], ...]
    date_sha256: Digest | None
    metrics: tuple[RunMetric, ...]
    limitations: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def unique_metrics(self) -> Self:
        identities = {(metric.method, metric.seed) for metric in self.metrics}
        if len(identities) != len(self.metrics):
            raise ValueError("Method and seed identities must be unique within a run")
        return self


class CatalogItem(Contract):
    run_id: Digest
    bundle_path: Text
    verified: bool
    record: VerifiedRun | None
    problem: str | None = None


class PairMetric(Contract):
    left_run_id: Digest
    right_run_id: Digest
    method: Text
    seed: int | None
    definition: MetricDefinition
    left: MetricValues | None
    right: MetricValues | None
    right_minus_left_rmse_bp: float | None


class ComparisonIssue(Contract):
    left_run_id: Digest
    right_run_id: Digest
    field: Text
    reason: Text


class RunComparison(Contract):
    comparable: bool
    runs: tuple[VerifiedRun, ...]
    pairs: tuple[PairMetric, ...]
    issues: tuple[ComparisonIssue, ...]
    winner: None = None
    interpretation: Literal[
        "Descriptive paired comparison; no default winner or execution authority"
    ] = "Descriptive paired comparison; no default winner or execution authority"


def json_digest(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
