from __future__ import annotations

from typing import Any

from papers.domain import InvestigationPlan, render_investigation_plan_markdown


def render_report(data: dict[str, Any], plan: InvestigationPlan) -> str:
    lines = [
        "# Investigating retained JEPA finance gaps and ideas",
        "",
        "This is a retained evidence synthesis plus an unexecuted investigation plan. No new "
        "literature search, model training, or backtest was performed.",
        "",
        render_investigation_plan_markdown(plan),
        "",
        "## Retained Evidence Coverage",
        "",
        "| Record | Role | Covered features |",
        "| --- | --- | --- |",
    ]
    for row in data["coverage_matrix"]:
        lines.append(
            f"| `{row['record_id']}` | {row['corpus_role']} | {', '.join(row['features'])} |"
        )
    lines.extend(["", "## Investigable Gaps", ""])
    for gap in data["gaps"]:
        lines.extend(
            [
                f"### {gap['gap_id']}: {gap['title']}",
                "",
                str(gap["inference"]),
                "",
                "Evidence:",
                *[
                    f"- `{evidence['fact_id']}` ([{evidence['record_id']}]"
                    f"(cited-excerpts/{evidence['record_id']}.md)): {evidence['claim']}"
                    for evidence in gap["supporting_evidence"]
                ],
                f"- Limitation: {gap['uncertainty']}",
                "",
            ]
        )
    lines.extend(["## Retained Hypotheses and Tests", ""])
    for hypothesis in data["retained_hypotheses"]:
        experiment = hypothesis["experiment"]
        lines.extend(
            [
                f"### {hypothesis['hypothesis_id']}: {hypothesis['title']}",
                "",
                str(hypothesis["mechanistic_bridge"]),
                "",
                f"- Experiment and baselines: {experiment['design']}",
                f"- Primary metric: {experiment['primary_metric']}",
                f"- Secondary metrics: {', '.join(experiment['secondary_metrics'])}",
                f"- Reject condition: {experiment['reject_condition']}",
                f"- Prior-art overlap: {hypothesis['overlap_caveat']}",
                f"- Remaining question: {hypothesis['remaining_question']}",
                "",
            ]
        )
    lines.extend(["## Limitations", "", *[f"- {item}" for item in data["limitations"]], ""])
    return "\n".join(lines)
