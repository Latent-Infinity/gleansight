from __future__ import annotations

import statistics

from pydantic import JsonValue, TypeAdapter

from research.financial_jepa.capacity_models import Trial


def summary(trials: tuple[Trial, ...]) -> dict[str, JsonValue]:
    methods: dict[str, JsonValue] = {}
    for name in sorted({trial.method for trial in trials}):
        observed = [trial for trial in trials if trial.method == name]
        values = [
            trial.rmse_bp
            for trial in observed
            if trial.status == "ok" and trial.rmse_bp is not None
        ]
        methods[name] = {
            "successful_seeds": len(values),
            "failed_seeds": len(observed) - len(values),
            "mean_rmse_bp": statistics.mean(values) if values else None,
            "sample_sd_rmse_bp": statistics.stdev(values) if len(values) > 1 else None,
            "minimum_rmse_bp": min(values) if values else None,
            "maximum_rmse_bp": max(values) if values else None,
        }
    paired: list[JsonValue] = []
    for selected, reference in (
        ("selected_current_pca", "random_current_pca"),
        ("selected_current_pca", "raw_current"),
        ("selected_predicted", "random_predicted"),
        ("selected_predicted", "raw_history_pca"),
    ):
        differences: list[float] = []
        included: list[JsonValue] = []
        seeds = sorted({trial.seed for trial in trials})
        for seed in seeds:
            values = {
                trial.method: trial.rmse_bp
                for trial in trials
                if trial.seed == seed and trial.status == "ok" and trial.rmse_bp is not None
            }
            if selected in values and reference in values:
                differences.append(values[selected] - values[reference])
                included.append(seed)
        paired.append(
            {
                "selected": selected,
                "reference": reference,
                "paired_seeds": included,
                "excluded_seed_count": len(seeds) - len(included),
                "mean_selected_minus_reference_rmse_bp": statistics.mean(differences)
                if differences
                else None,
                "sample_sd_difference_bp": statistics.stdev(differences)
                if len(differences) > 1
                else None,
                "per_seed_differences_bp": list(differences),
            }
        )
    return {
        "methods": methods,
        "paired": paired,
        "failures": [
            TypeAdapter(dict[str, JsonValue]).validate_python(trial.model_dump(mode="json"))
            for trial in trials
            if trial.status == "failed"
        ],
    }


def render_report(trials: tuple[Trial, ...], aggregate: dict[str, JsonValue]) -> str:
    lines = [
        "# Matched YieldJEPA development diagnostics",
        "",
        "Training: 2001–2017. Checkpoint and ridge selection: 2018–2021. "
        "These are development-selection results.",
        "No held-out, significance, profitability, causality, model-winner "
        "or paper-replication claim is supported.",
        "",
        "Current group: identical last-curve eight observations; eight readout features; "
        "360 ridge coefficients/intercepts.",
        "History group: identical 30×8 observation windows; sixteen features per horizon; "
        "680 ridge coefficients/intercepts.",
        "Dates, targets, seeds, alpha grid and ridge fitting are shared. "
        "Encoder parameter counts and pretraining capacity are not matched.",
        "PCA fits standardized training features only. Compression loses information; "
        "retained variance and numerical feature rank are reported separately.",
        "The selected source checkpoints already used the selection interval. "
        "They are not out-of-sample fold models.",
        "",
        "| Method | Seed | Status | RMSE bp | Rank | PCA retained variance | Failure |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for trial in trials:
        lines.append(
            f"| {trial.method} | {trial.seed} | {trial.status} | {trial.rmse_bp} | "
            f"{trial.training_feature_rank} | {trial.projection_variance_retained} | "
            f"{trial.error or ''} |"
        )
    lines.extend(
        (
            "",
            "## Paired and aggregate variation",
            "",
            "Seed variation is descriptive; repeated deterministic raw baselines "
            "are not independent replications.",
            "All failures and excluded pairs remain visible; "
            "no successful-only winner ranking is produced.",
            "",
            "```json",
        )
    )
    import json

    lines.extend((json.dumps(aggregate, indent=2, sort_keys=True), "```", ""))
    return "\n".join(lines)
