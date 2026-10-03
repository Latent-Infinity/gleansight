from __future__ import annotations

from pathlib import Path

from papers.domain.ideation_bundle import atomic_bundle, write_manifest
from research.catalog.models import RunComparison


def write_comparison(root: Path, report: RunComparison) -> Path:
    lines = [
        "# Verified research comparison",
        "",
        report.interpretation,
        "",
        f"Comparable: {report.comparable}. No winner is selected.",
        "",
        "| Run | Workflow / classification | Verification |",
        "|---|---|---|",
    ]
    for run in report.runs:
        lines.append(
            f"| {run.run_id} | {run.workflow} / {run.classification} | {run.verification} |"
        )
    for run in report.runs:
        lines.extend(
            [
                "",
                f"## Run {run.run_id}",
                "",
                f"Source SHA256: {run.source_sha256}",
                f"Protocol SHA256: {run.protocol_sha256}",
                f"Split SHA256: {run.split_sha256}",
                f"Code SHA256: {run.code_sha256}",
                f"Paired seeds: {run.seeds}",
                f"Paired origin dates: {len(run.origin_dates)}; exact dates "
                f"are in comparison.json.",
            ]
        )
    if report.issues:
        lines.extend(["", "## Incomparable identities", ""])
        lines.extend(
            f"- {issue.left_run_id} / {issue.right_run_id}: {issue.reason}"
            for issue in report.issues
        )
    if report.pairs:
        lines.extend(
            [
                "",
                "## Paired descriptive RMSE",
                "",
                "Units: basis points. RMSE is 100 × square root of the mean "
                "squared raw yield error in percentage points.",
                "Exact dates, horizon/tenor axes, metric definitions, and "
                "artifact identities are retained in comparison.json.",
                "",
                "| Left run / right run | Method | Seed | Left RMSE | Right "
                "RMSE | Right minus left |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in report.pairs:
            left = str(row.left.overall_rmse_bp) if row.left is not None else "failed"
            right = str(row.right.overall_rmse_bp) if row.right is not None else "failed"
            lines.append(
                f"| {row.left_run_id[:12]} / {row.right_run_id[:12]} | "
                f"{row.method} | {row.seed} | {left} | {right} | {row.right_minus_left_rmse_bp} |"
            )
    with atomic_bundle(root, "research-comparison") as (staging, published):
        (staging / "comparison.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        (staging / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_manifest(staging, ("comparison.json", "report.md"))
    return published
