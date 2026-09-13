from __future__ import annotations

from research.financial_jepa.contracts import (
    CollapseDiagnostics,
    JsonValue,
    MetricSummary,
    PreparedSplits,
    Variant,
)
from research.financial_jepa.protocol import protocol_record as protocol_record
from research.financial_jepa.report import aggregate, verdict
from research.financial_jepa.report import report_text as report_text
from research.financial_jepa.report_types import (
    BaselineResults as BaselineResults,
)
from research.financial_jepa.report_types import (
    FitOutcome as FitOutcome,
)
from research.financial_jepa.report_types import (
    RidgeIdentity as RidgeIdentity,
)


def metric_record(metrics: MetricSummary) -> dict[str, JsonValue]:
    horizons: list[JsonValue] = list(metrics.per_horizon_rmse_bp)
    tenors: list[JsonValue] = list(metrics.per_tenor_rmse_bp)
    matrix: list[JsonValue] = []
    for row in metrics.matrix_rmse_bp:
        matrix_row: list[JsonValue] = list(row)
        matrix.append(matrix_row)
    record: dict[str, JsonValue] = {
        "overall_rmse_bp": metrics.overall_rmse_bp,
        "per_horizon_rmse_bp": horizons,
        "per_tenor_rmse_bp": tenors,
        "matrix_rmse_bp": matrix,
    }
    return record


def _diagnostic_record(value: CollapseDiagnostics) -> dict[str, JsonValue]:
    return {
        "mean_sample_std": value.mean_sample_std,
        "effective_rank": value.effective_rank,
        "heuristic_collapse": value.collapsed,
    }


def _fit_record(value: FitOutcome) -> dict[str, JsonValue]:
    identity: dict[str, JsonValue] = {
        "shared_alpha": value.ridge_alpha,
        "coefficients_sha256": value.readout_identity.coefficients_sha256,
        "feature_scalers_sha256": value.readout_identity.feature_scaler_sha256,
        "intercepts_sha256": value.readout_identity.intercept_sha256,
        "combined_sha256": value.readout_identity.combined_sha256,
    }
    return {
        "variant": value.variant.value,
        "seed": value.seed,
        "selected_epoch": value.selected_epoch,
        "aligned_validation_latent_mse": value.validation_mse,
        "checkpoint_sha256": value.checkpoint_sha256,
        "ridge_alpha": value.ridge_alpha,
        "readout_sha256": value.readout_sha256,
        "readout_identity": identity,
        "test_raw_overall_rmse_bp": value.evaluation.raw_metrics.overall_rmse_bp,
        "raw_metrics": metric_record(value.evaluation.raw_metrics),
        "latent_mse": value.evaluation.latent_mse,
        "latent_persistence_mse": value.evaluation.latent_persistence_mse,
        "date_sha256": value.evaluation.date_sha256,
        "diagnostics": {
            "train": _diagnostic_record(value.train_diagnostic),
            "validation": _diagnostic_record(value.validation_diagnostic),
            "test": _diagnostic_record(value.test_diagnostic),
        },
    }


def _baseline_record(value: BaselineResults) -> dict[str, JsonValue]:
    direct = metric_record(value.direct_ridge)
    direct["alpha"] = value.direct_alpha
    direct["model_identity"] = {
        "alpha": value.direct_alpha,
        "coefficients_sha256": value.direct_identity.coefficients_sha256,
        "feature_scaler_sha256": value.direct_identity.feature_scaler_sha256,
        "intercept_sha256": value.direct_identity.intercept_sha256,
        "combined_sha256": value.direct_identity.combined_sha256,
    }
    return {
        "date_sha256": value.date_sha256,
        "last_level_persistence": metric_record(value.persistence),
        "training_row_mean": metric_record(value.training_mean),
        "direct_ridge": direct,
    }


def _dataset_record(prepared: PreparedSplits) -> dict[str, JsonValue]:
    record: dict[str, JsonValue] = {}
    for name, split in (
        ("train", prepared.train),
        ("validation", prepared.validation),
        ("test", prepared.test),
    ):
        gaps: list[JsonValue] = []
        for days, count in split.gap_histogram:
            gap: dict[str, JsonValue] = {"calendar_days": days, "count": count}
            gaps.append(gap)
        split_record: dict[str, JsonValue] = {
            "retained_row_count": len(split.unique_rows),
            "window_count": len(split.windows),
            "segment_count": split.segment_count,
            "discarded_window_count": split.discarded_window_count,
            "gap_histogram": gaps,
        }
        record[name] = split_record
    return record


def results_record(
    fits: tuple[FitOutcome, ...],
    baselines: BaselineResults,
    variants: tuple[Variant, ...],
    prepared: PreparedSplits,
) -> tuple[dict[str, JsonValue], str]:
    aggregates = {variant: aggregate(fits, variant) for variant in variants}
    result, failed = verdict(fits, aggregates, baselines)
    aggregate_record: dict[str, JsonValue] = {}
    for variant, values in aggregates.items():
        summary: dict[str, JsonValue] = {
            "mean_rmse_bp": values[0],
            "std_rmse_bp": values[1],
        }
        aggregate_record[variant.value] = summary
    fit_records: list[JsonValue] = [_fit_record(fit) for fit in fits]
    failures: list[JsonValue] = [failure for failure in failed]
    record: dict[str, JsonValue] = {
        "fits": fit_records,
        "aggregates": aggregate_record,
        "raw_baselines": _baseline_record(baselines),
        "dataset_accounting": _dataset_record(prepared),
        "verdict": result,
        "failed_predeclared_conditions": failures,
    }
    return record, result
