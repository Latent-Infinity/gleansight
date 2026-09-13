from __future__ import annotations

from dataclasses import dataclass

from research.financial_jepa.contracts import CollapseDiagnostics, MetricSummary, Variant
from research.financial_jepa.evaluation import EvaluationResult


@dataclass(frozen=True, slots=True)
class RidgeIdentity:
    coefficients_sha256: str
    feature_scaler_sha256: str
    intercept_sha256: str
    combined_sha256: str


@dataclass(frozen=True, slots=True)
class BaselineResults:
    date_sha256: str
    persistence: MetricSummary
    training_mean: MetricSummary
    direct_ridge: MetricSummary
    direct_alpha: float
    direct_identity: RidgeIdentity


@dataclass(frozen=True, slots=True)
class FitOutcome:
    variant: Variant
    seed: int
    selected_epoch: int
    validation_mse: float
    checkpoint_sha256: str
    ridge_alpha: float
    readout_sha256: str
    readout_identity: RidgeIdentity
    evaluation: EvaluationResult
    train_diagnostic: CollapseDiagnostics
    validation_diagnostic: CollapseDiagnostics
    test_diagnostic: CollapseDiagnostics
