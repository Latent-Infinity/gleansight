from __future__ import annotations

import numpy as np

from research.financial_jepa.contracts import Variant
from research.financial_jepa.report_types import BaselineResults, FitOutcome


def aggregate(fits: tuple[FitOutcome, ...], variant: Variant) -> tuple[float, float]:
    values = np.asarray(
        [fit.evaluation.raw_metrics.overall_rmse_bp for fit in fits if fit.variant is variant],
        dtype=np.float64,
    )
    return float(values.mean()), float(values.std(ddof=0))


def verdict(
    fits: tuple[FitOutcome, ...],
    aggregates: dict[Variant, tuple[float, float]],
    baselines: BaselineResults,
) -> tuple[str, list[str]]:
    baseline_values = (
        baselines.persistence.overall_rmse_bp,
        baselines.training_mean.overall_rmse_bp,
        baselines.direct_ridge.overall_rmse_bp,
    )
    conditions = {
        "regularized_mean_beats_all_raw_baselines": (
            aggregates[Variant.REGULARIZED][0] < min(baseline_values)
        ),
        "every_regularized_seed_beats_paired_shuffle": all(
            next(
                row.evaluation.raw_metrics.overall_rmse_bp
                for row in fits
                if row.variant is Variant.REGULARIZED and row.seed == seed
            )
            < next(
                row.evaluation.raw_metrics.overall_rmse_bp
                for row in fits
                if row.variant is Variant.SHUFFLED_TARGET and row.seed == seed
            )
            for seed in (17, 29, 43)
        ),
        "every_regularized_latent_beats_persistence": all(
            row.evaluation.latent_mse < row.evaluation.latent_persistence_mse
            for row in fits
            if row.variant is Variant.REGULARIZED
        ),
        "no_regularized_collapse": all(
            not (
                row.train_diagnostic.collapsed
                or row.validation_diagnostic.collapsed
                or row.test_diagnostic.collapsed
            )
            for row in fits
            if row.variant is Variant.REGULARIZED
        ),
    }
    failed = [name for name, passed in conditions.items() if not passed]
    return ("preliminary_descriptive_signal" if not failed else "negative_or_inconclusive"), failed


def report_text(
    fits: tuple[FitOutcome, ...],
    baselines: BaselineResults,
    variants: tuple[Variant, ...],
) -> str:
    aggregates = {variant: aggregate(fits, variant) for variant in variants}
    result, failed = verdict(fits, aggregates, baselines)
    lines = [
        "# YieldJEPA independent mechanism study",
        "",
        f"Verdict: **{result}**.",
        "",
        "## Raw Baselines",
        "",
        f"- Last-level persistence: {baselines.persistence.overall_rmse_bp:.6f} bp",
        f"- Training-row mean: {baselines.training_mean.overall_rmse_bp:.6f} bp",
        (
            f"- Direct ridge: {baselines.direct_ridge.overall_rmse_bp:.6f} bp "
            f"(alpha={baselines.direct_alpha:g})"
        ),
        "",
        "## Per-seed JEPA Results",
        "",
    ]
    for fit in fits:
        collapse = any(
            diagnostic.collapsed
            for diagnostic in (
                fit.train_diagnostic,
                fit.validation_diagnostic,
                fit.test_diagnostic,
            )
        )
        lines.append(
            f"- {fit.variant.value}, seed {fit.seed}: raw RMSE "
            f"{fit.evaluation.raw_metrics.overall_rmse_bp:.6f} bp; latent MSE "
            f"{fit.evaluation.latent_mse:.6f}; own latent persistence "
            f"{fit.evaluation.latent_persistence_mse:.6f}; collapse={str(collapse).lower()}"
        )
    lines.extend(["", "## Aggregate RMSE", ""])
    for variant in variants:
        mean, std = aggregates[variant]
        lines.append(f"- {variant.value}: {mean:.6f} +/- {std:.6f} bp (population std)")
    lines.extend(["", "## Collapse Diagnostics", ""])
    for fit in fits:
        for split, diagnostic in (
            ("train", fit.train_diagnostic),
            ("validation", fit.validation_diagnostic),
            ("test", fit.test_diagnostic),
        ):
            lines.append(
                f"- {fit.variant.value}, seed {fit.seed}, {split}: mean sample std "
                f"{diagnostic.mean_sample_std:.6f}; effective rank "
                f"{diagnostic.effective_rank:.6f}; collapsed={str(diagnostic.collapsed).lower()}"
            )
    lines.extend(["", "## Failed Predeclared Conditions", ""])
    lines.extend(f"- {condition}" for condition in failed)
    if not failed:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Independent Treasury-yield mechanism study, not an exact Fin-JEPA replication.",
            (
                "- Descriptive forecast evidence only; no trading, return, Sharpe, "
                "significance, or government-endorsement claim."
            ),
            "- Private original code, data, and checkpoints were unavailable.",
            "",
        ]
    )
    return "\n".join(lines)
