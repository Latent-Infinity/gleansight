from pathlib import Path
from types import FunctionType

import flet as ft
import pytest

from papers.app.use_cases.citation_exports import ExportPapersUseCase
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloProjectStore,
)
from papers.ui.components.citation_exports import CitationExportControls


def controls(root: ft.Control) -> list[ft.Control]:
    descendants = [root]
    for child in getattr(root, "controls", []):
        descendants.extend(controls(child))
    return descendants


@pytest.mark.parametrize(
    "scope", ["selected", "project", "empty", "unavailable", "missingproject", "unknownproject"]
)
def test_desktop_export_controls(tmp_path: Path, scope: str) -> None:
    db = PiccoloDatabase(tmp_path / "papers.sqlite")
    db.initialize_schema()
    PiccoloPaperStore().create_paper({"paper_id": "paper-1", "title": "Desktop export"})
    projects = PiccoloProjectStore()
    projects.create_project("project-1", "Cohort")
    PiccoloPaperProjectStore().attach("paper-1", "project-1")
    messages: list[tuple[str, bool]] = []
    component = CitationExportControls(
        None if scope == "unavailable" else ExportPapersUseCase(db, tmp_path / "exports"),
        lambda text, error: messages.append((text, error)),
    )
    checkbox = component.checkbox("paper-1")
    checkbox.value = True
    assert isinstance(checkbox.on_change, FunctionType)
    checkbox.on_change(ft.Event(control=checkbox, name="change", data="true"))
    assert component.selected_ids == {"paper-1"}
    checkbox.value = False
    checkbox.on_change(ft.Event(control=checkbox, name="change", data="false"))
    assert not component.selected_ids
    if scope == "selected":
        component.selected_ids.add("paper-1")
    rendered = controls(component.build())
    if scope in {"project", "missingproject", "unknownproject"}:
        for control in rendered:
            if isinstance(control, ft.Dropdown) and control.label == "Export scope":
                control.value = "project"
            if isinstance(control, ft.TextField):
                control.value = (
                    ""
                    if scope == "missingproject"
                    else ("absent" if scope == "unknownproject" else "project-1")
                )
    button = next(control for control in rendered if isinstance(control, ft.OutlinedButton))
    assert isinstance(button.on_click, FunctionType)
    button.on_click(ft.Event(control=button, name="click", data=""))
    assert messages[-1][1] == (
        scope in {"empty", "unavailable", "missingproject", "unknownproject"}
    )
    assert bool(list((tmp_path / "exports").glob("*/manifest.json"))) == (
        scope in {"selected", "project"}
    )
