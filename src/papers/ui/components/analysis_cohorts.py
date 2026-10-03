"""Named saved baseline/revision selections for the current paper."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from papers.domain.analysis_comparison import (
    CohortReport,
    CohortSelection,
    SavedCohort,
)
from papers.domain.errors import NotFoundError
from papers.ui.components.analysis_review import comparison_view


@dataclass(frozen=True, slots=True)
class CohortActions:
    save: Callable[[CohortSelection], SavedCohort]
    compare: Callable[[str], CohortReport]
    list: Callable[[], tuple[SavedCohort, ...]]
    selection: Callable[[], CohortSelection]


def build_cohort_controls(actions: CohortActions) -> ft.Control:
    """Save current run choices; reopen exact saved choices after a restart."""
    name = ft.TextField(label="Evaluation cohort name", width=350)
    saved = ft.Dropdown(label="Saved evaluation cohort", width=350)
    result = ft.Column([], spacing=8)

    def refresh() -> None:
        saved.options = [
            ft.dropdown.Option(cohort.cohort_id, cohort.selection.name) for cohort in actions.list()
        ]

    def save(_: ft.Event[ft.Button]) -> None:
        try:
            cohort_name = (name.value or "").strip()
            if not cohort_name:
                message = "Enter a name for this evaluation cohort."
                raise ValueError(message)
            selection = actions.selection()
            named = CohortSelection(
                name=cohort_name,
                project_id=selection.project_id,
                baseline_prompt_version_id=selection.baseline_prompt_version_id,
                revised_prompt_version_id=selection.revised_prompt_version_id,
                pairs=selection.pairs,
            )
            cohort = actions.save(named)
            refresh()
            saved.value = cohort.cohort_id
            saved.update()
            result.controls = [ft.Text(f"Saved cohort: {cohort.cohort_id}", selectable=True)]
        except (NotFoundError, ValueError, OSError) as exc:
            result.controls = [ft.Text(str(exc), color=ft.Colors.RED_700)]
        result.update()

    def compare(_: ft.Event[ft.Button]) -> None:
        try:
            if not saved.value:
                message = "Choose a saved evaluation cohort."
                raise ValueError(message)
            report = actions.compare(saved.value)
            result.controls = [
                ft.Text(f"Cohort: {report.cohort.cohort_id}", selectable=True),
                *[comparison_view(item) for item in report.comparisons],
            ]
        except (NotFoundError, ValueError, OSError) as exc:
            result.controls = [ft.Text(str(exc), color=ft.Colors.RED_700)]
        result.update()

    refresh()
    return ft.Column(
        [
            ft.Text("Saved evaluation cohorts", size=14, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Save the selected baseline and revised runs for this paper. "
                "Existing outputs stay unchanged."
            ),
            ft.Row([name, ft.Button("Save selected runs", on_click=save)], wrap=True),
            ft.Row([saved, ft.Button("Compare saved cohort", on_click=compare)], wrap=True),
            result,
        ],
        spacing=8,
    )
