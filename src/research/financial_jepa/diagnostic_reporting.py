from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from research.financial_jepa.contracts import JsonValue
from research.financial_jepa.diagnostic_contracts import (
    DIAGNOSTIC_PROTOCOL_VERSION,
    DiagnosticConfig,
)

_JSON_RECORD_ADAPTER: Final = TypeAdapter(dict[str, JsonValue])


def diagnostic_protocol(config: DiagnosticConfig) -> dict[str, JsonValue]:
    return _JSON_RECORD_ADAPTER.validate_python(
        {
            "protocol_version": DIAGNOSTIC_PROTOCOL_VERSION,
            "status": config.label,
            "dataset": {
                "years": list(config.years),
                "splits": {"train": "2001-2017", "validation": "2018-2021"},
                "offline_default": True,
                "scaler_fit": "retained_training_rows_only",
            },
            "window": {"context": config.context_length, "future": config.future_length},
            "training": {
                "variant": "regularized",
                "seeds": list(config.seeds),
                "epochs": config.epochs,
                "batch_size": config.batch_size,
                "optimizer": "original_AdamW",
                "ema_decay": 0.99,
            },
            "methods": {
                "forecast": [
                    "raw_history",
                    "selected_ema_current",
                    "predicted_future",
                    "frozen_random_current",
                ],
                "alpha_grid": list(config.ridge_alphas),
                "alpha_policy": "one_shared_alpha_per_method_seed_all_horizons",
                "refit_train_plus_validation": False,
                "orientation_baseline": "last_level_persistence",
            },
            "interpretation": {
                "selection_label": "development_selection",
                "claims_forbidden": ["heldout", "winner", "causal", "profitability"],
                "raw_history_capacity": "240 inputs; not capacity-matched to 16-dimensional probes",
                "random_comparison": "paired by neural seed and exact initial EMA encoder",
            },
        }
    )


def report_text(results: dict[str, JsonValue]) -> str:
    lines = [
        "# YieldJEPA development diagnostics",
        "",
        "All metrics are **development_selection** estimates selected on 2018-2021 "
        "validation data.",
        "They are not held-out estimates and support no winner, causal, significance, "
        "or profit claim.",
        "",
        "## Forecast diagnostics",
        "",
    ]
    methods = results["methods"]
    if isinstance(methods, dict):
        raw = methods["raw_history"]
        if isinstance(raw, dict):
            lines.append(f"- raw_history: {raw['overall_rmse_bp']} bp")
    seeds = results["seeds"]
    if isinstance(seeds, list):
        for seed in seeds:
            if not isinstance(seed, dict):
                continue
            method_rows = seed["methods"]
            if not isinstance(method_rows, dict):
                continue
            for name, values in method_rows.items():
                if isinstance(values, dict):
                    lines.append(f"- {name}, seed {seed['seed']}: {values['overall_rmse_bp']} bp")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Frozen-random comparisons are paired by seed using the exact captured "
            "initial EMA encoder.",
            "- Raw history uses 240 inputs and is not capacity-matched to 16-dimensional probes.",
            "- Better latent error with worse raw forecasts can indicate decodability mismatch.",
            "",
        ]
    )
    return "\n".join(lines)


def code_identity(repo_root: Path) -> dict[str, JsonValue]:
    paths = [
        *sorted((repo_root / "src/research/financial_jepa").glob("*.py")),
        repo_root / "scripts/diagnose_financial_jepa.py",
        repo_root / "src/nsqd/infrastructure/workflow_output.py",
        repo_root / "pyproject.toml",
        repo_root / "uv.lock",
    ]
    files: dict[str, JsonValue] = {}
    combined = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(repo_root).as_posix()
        content = path.read_bytes()
        files[relative] = hashlib.sha256(content).hexdigest()
        combined.update(relative.encode())
        combined.update(content)
    return {"sha256": combined.hexdigest(), "files": files}
