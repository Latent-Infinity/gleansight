"""Stored output inspection controls using the paper detail screen's Flet primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from papers.domain.analysis_comparison import (
    ArtifactView,
    CohortReport,
    CohortSelection,
    ExtractedValue,
    RunComparison,
    RunInspection,
    RunPair,
    SavedCohort,
)
from papers.domain.errors import NotFoundError


def _output(label: str, artifact: ArtifactView) -> ft.Control:
    return ft.ExpansionTile(
        title=ft.Text(f"{label}: {artifact.state}"),
        controls=[ft.Text(artifact.error or artifact.text or "(empty output)", selectable=True)],
    )


def inspection_view(run: RunInspection) -> ft.Control:
    """Keep identities, validation and unknown usage visible next to stored output."""
    cost = f"${run.cost_usd:.4f} recorded" if run.cost_usd is not None else "unknown"
    return ft.Column(
        [
            ft.Text(f"Run: {run.run_id}", weight=ft.FontWeight.BOLD, selectable=True),
            ft.Text(
                f"Paper: {run.paper_id} · Prompt version: {run.prompt_version_id}", selectable=True
            ),
            ft.Text(f"Status: {run.status} · Model: {run.model_name}", selectable=True),
            ft.Text(
                f"Tokens in/out: {run.tokens_in if run.tokens_in is not None else 'unknown'}/"
                f"{run.tokens_out if run.tokens_out is not None else 'unknown'} · Cost: {cost}"
            ),
            ft.Text(f"Error: {run.error_message or 'none'}", selectable=True),
            ft.Text(f"Validation: {run.validation_issues or 'none recorded'}", selectable=True),
            _output("Text output", run.output_md),
            _output("JSON output", run.output_json),
        ],
        spacing=8,
    )


def _value(extraction: ExtractedValue | None) -> str:
    if extraction is None:
        return "(absent)"
    for value in (extraction.value_text, extraction.value_numeric, extraction.value_boolean):
        if value is not None:
            return str(value)
    return "(recorded null)"


def comparison_view(comparison: RunComparison) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Text(
            "Schema changed" if comparison.schema_changed else "Schema unchanged",
            weight=ft.FontWeight.BOLD,
        ),
        ft.Text(comparison.interpretation),
        inspection_view(comparison.baseline),
        ft.Divider(),
        inspection_view(comparison.revised),
    ]
    for label, difference in (
        ("Output diff", comparison.output_diff),
        ("JSON output diff", comparison.json_output_diff),
        ("Schema diff", comparison.schema_diff),
    ):
        controls.extend(
            [
                ft.Text(label, weight=ft.FontWeight.BOLD),
                ft.Text(difference or "No differences.", selectable=True, font_family="monospace"),
            ]
        )
    controls.append(ft.Text("Extraction differences", weight=ft.FontWeight.BOLD))
    labels = {
        "missing_baseline": "absent from baseline",
        "missing_revised": "absent from revision",
        "changed": "changed",
        "unchanged": "unchanged",
    }
    for item in comparison.extraction_diff:
        controls.append(
            ft.Text(
                f"{item.field_path} · {labels[item.change]} · {item.entity_type}"
                f"{': ' + item.entity_ref if item.entity_ref else ''}\n"
                f"Baseline: {_value(item.baseline)}\nRevised: {_value(item.revised)}",
                selectable=True,
            )
        )
    if not comparison.extraction_diff:
        controls.append(ft.Text("No extracted fields recorded."))
    return ft.Column(controls, spacing=8)


@dataclass(frozen=True, slots=True)
class AnalysisReviewActions:
    inspect: Callable[[str], RunInspection]
    compare: Callable[[str, str], RunComparison]
    save_cohort: Callable[[CohortSelection], SavedCohort] | None = None
    compare_cohort: Callable[[str], CohortReport] | None = None
    list_cohorts: Callable[[], tuple[SavedCohort, ...]] | None = None


def build_analysis_review(
    run_ids: tuple[str, ...],
    actions: AnalysisReviewActions,
) -> ft.Control:
    """Open either selected run or compare two explicit IDs without invoking a model."""
    baseline = ft.Dropdown(
        label="Baseline run",
        value=run_ids[0] if run_ids else None,
        options=[ft.dropdown.Option(value) for value in run_ids],
        width=350,
    )
    revised = ft.Dropdown(
        label="Revised run",
        value=run_ids[1] if len(run_ids) > 1 else None,
        options=[ft.dropdown.Option(value) for value in run_ids],
        width=350,
    )
    result = ft.Column([], spacing=8)

    def open_run(selector: ft.Dropdown) -> None:
        try:
            if not selector.value:
                message = "Select a run to inspect."
                raise ValueError(message)
            result.controls = [inspection_view(actions.inspect(selector.value))]
        except (NotFoundError, ValueError, OSError) as exc:
            result.controls = [ft.Text(str(exc), color=ft.Colors.RED_700)]
        result.update()

    def compare(_: ft.Event[ft.Button]) -> None:
        try:
            if not baseline.value or not revised.value:
                message = "Select a baseline and a revised run."
                raise ValueError(message)
            result.controls = [comparison_view(actions.compare(baseline.value, revised.value))]
        except (NotFoundError, ValueError, OSError) as exc:
            result.controls = [ft.Text(str(exc), color=ft.Colors.RED_700)]
        result.update()

    panel = ft.Column(
        [
            ft.Text("Inspect stored analysis", size=14, weight=ft.FontWeight.BOLD),
            ft.Row([baseline, revised], wrap=True),
            ft.Row(
                [
                    ft.Button("Open baseline output", on_click=lambda _: open_run(baseline)),
                    ft.Button("Open revised output", on_click=lambda _: open_run(revised)),
                    ft.Button("Compare runs", on_click=compare),
                ],
                wrap=True,
            ),
            result,
        ],
        spacing=8,
    )

    save_cohort = actions.save_cohort
    compare_cohort = actions.compare_cohort
    list_cohorts = actions.list_cohorts
    if save_cohort is not None and compare_cohort is not None and list_cohorts is not None:
        from papers.ui.components.analysis_cohorts import CohortActions, build_cohort_controls

        def selection() -> CohortSelection:
            left = actions.inspect(baseline.value or "")
            right = actions.inspect(revised.value or "")
            return CohortSelection(
                name="Selected paper",
                baseline_prompt_version_id=left.prompt_version_id,
                revised_prompt_version_id=right.prompt_version_id,
                pairs=(RunPair(baseline_run_id=left.run_id, revised_run_id=right.run_id),),
            )

        panel.controls.append(
            build_cohort_controls(
                CohortActions(
                    save=save_cohort, compare=compare_cohort, list=list_cohorts, selection=selection
                )
            )
        )
    return panel
