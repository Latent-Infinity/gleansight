from types import FunctionType

import flet as ft

from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.ui.components.screening import ScreeningControls
from tests.screening.conftest import LocalScholar


def descendants(control: ft.Control) -> list[ft.Control]:
    found = [control]
    for child in getattr(control, "controls", []):
        found.extend(descendants(child))
    return found


def click(root: ft.Control, label: str) -> None:
    button = next(
        item for item in descendants(root) if isinstance(item, ft.Button) and item.content == label
    )
    assert isinstance(button.on_click, FunctionType)
    button.on_click(ft.Event(control=button, name="click", data=""))


def test_desktop_saved_screening_workflow(
    configuration: ApiConfiguration, scholar: LocalScholar
) -> None:
    service = SavedDiscoveryService(ApiRuntime(configuration).paper_database, scholar)
    root = ScreeningControls(
        service, lambda: [{"project_id": "project-1", "name": "Literature review"}]
    ).build()
    values = {
        "Project": "project-1",
        "Search name": "Desktop query",
        "Saved query": "causal",
        "Reviewer": "Desktop reader",
        "Rationale": "Relevant methods",
        "Decision": "include",
    }
    for control in descendants(root):
        if isinstance(control, (ft.TextField, ft.Dropdown)) and control.label in values:
            control.value = values[control.label]
    click(root, "Save new search")
    search = service.list()[0]
    click(root, "Rerun saved query")
    checkbox = next(item for item in descendants(root) if isinstance(item, ft.Checkbox))
    checkbox.value = True
    assert isinstance(checkbox.on_change, FunctionType)
    checkbox.on_change(ft.Event(control=checkbox, name="change", data="true"))
    click(root, "Record screening")
    assert service.get(search.search_id).reviews[0].decision == "include"
    checkbox = next(item for item in descendants(root) if isinstance(item, ft.Checkbox))
    checkbox.value = True
    assert isinstance(checkbox.on_change, FunctionType)
    checkbox.on_change(ft.Event(control=checkbox, name="change", data="true"))
    click(root, "Import selected inclusions")
    click(root, "Schedule from tomorrow")
    database = service.database
    assert database.fetchall("SELECT paper_id FROM paper_projects WHERE project_id='project-1'")
    assert database.fetchall("SELECT job_id FROM jobs WHERE type='discover' AND status='queued'")
    assert any(
        isinstance(item, ft.Text) and "Queued 1" in (item.value or "") for item in descendants(root)
    )


def test_desktop_empty_selection_has_visible_error(
    configuration: ApiConfiguration, scholar: LocalScholar
) -> None:
    root = ScreeningControls(
        SavedDiscoveryService(ApiRuntime(configuration).paper_database, scholar), lambda: []
    ).build()
    click(root, "Record screening")
    assert any(
        isinstance(item, ft.Text) and item.color == ft.Colors.RED_600 for item in descendants(root)
    )


def test_desktop_validation_error_names_fields_without_framework_details(
    configuration: ApiConfiguration, scholar: LocalScholar
) -> None:
    root = ScreeningControls(
        SavedDiscoveryService(ApiRuntime(configuration).paper_database, scholar), lambda: []
    ).build()
    click(root, "Save new search")
    message = next(
        item
        for item in descendants(root)
        if isinstance(item, ft.Text) and item.color == ft.Colors.RED_600
    )
    assert "project" in (message.value or "").lower()
    assert "pydantic" not in (message.value or "").lower()
