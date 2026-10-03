from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import flet as ft

from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.domain.analysis_comparison import RunPair
from papers.infra.analysis_cohorts import AnalysisCohortStore
from papers.ui.components.analysis_review import AnalysisReviewActions, build_analysis_review
from tests.app.use_cases.test_analysis_comparison import comparison as comparison
from tests.ui.test_paper_screen import _find_all, _find_text_values


def panel(comparison: AnalysisComparisonService) -> ft.Control:
    return build_analysis_review(
        ("run-1", "run-2"),
        AnalysisReviewActions(
            inspect=comparison.inspect,
            compare=lambda left, right: comparison.compare(
                RunPair(baseline_run_id=left, revised_run_id=right)
            ),
            save_cohort=comparison.save_cohort,
            compare_cohort=comparison.compare_cohort,
            list_cohorts=AnalysisCohortStore(comparison.database).list,
        ),
    )


def click(root: ft.Control, label: str) -> None:
    buttons = _find_all(root, ft.Button)
    button = next(button for button in buttons if button.content == label)
    assert button.on_click is not None
    with patch.object(ft.Control, "update", return_value=None):
        button.on_click(ft.Event("click", button))


def test_review_controls_open_failed_output_and_compare(
    comparison: AnalysisComparisonService, tmp_path: Path
) -> None:
    # Given mounted-equivalent controls with real database service callbacks.
    control = panel(comparison)
    # When the failed output is opened and both runs are compared.
    click(control, "Open revised output")
    opened = _find_text_values(control)
    click(control, "Compare runs")
    text = _find_text_values(control)
    # Then actual rendered control content carries outputs and provenance.
    assert any("failed" in value for value in opened)
    assert any("prompt-2" in value for value in opened)
    assert any("unknown" in value for value in opened)
    assert any("Schema changed" in value for value in text)
    assert any("absent from baseline" in value for value in text)
    assert any("-Output 1" in value for value in text)
    (tmp_path / "ui-comparison-controls.txt").write_text("\n".join(text))


def test_saved_cohort_controls_reopen_after_rebuild(comparison: AnalysisComparisonService) -> None:
    # Given current run selections and a user-entered cohort name.
    control = panel(comparison)
    name = next(
        field
        for field in _find_all(control, ft.TextField)
        if field.label == "Evaluation cohort name"
    )
    name.value = "Baseline check"
    # When saved then reopened from a rebuilt screen.
    click(control, "Save selected runs")
    restarted = panel(comparison)
    chooser = next(
        field
        for field in _find_all(restarted, ft.Dropdown)
        if field.label == "Saved evaluation cohort"
    )
    assert len(chooser.options) == 1
    chooser.value = chooser.options[0].key
    click(restarted, "Compare saved cohort")
    # Then saved exact run pairs drive the comparison.
    text = _find_text_values(restarted)
    assert any("Schema changed" in value for value in text)
    assert any("run-1" in value for value in text)
    assert any("run-2" in value for value in text)


def test_review_selection_errors_are_visible(comparison: AnalysisComparisonService) -> None:
    # Given unset selections.
    control = panel(comparison)
    for field in _find_all(control, ft.Dropdown):
        field.value = None
    # When each explicit action is invoked, then it gives a visible selection error.
    for label in (
        "Open baseline output",
        "Compare runs",
        "Compare saved cohort",
        "Save selected runs",
    ):
        click(control, label)
    assert any("Enter a name" in text for text in _find_text_values(control))
