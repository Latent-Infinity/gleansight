from types import FunctionType

import flet as ft
import pytest

from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.domain.screening import ReviewRequest, SaveSearch
from papers.ui.components.screening import ScreeningControls
from tests.screening.conftest import LocalScholar
from tests.screening.test_screening_ui import click, descendants


def panel(service: SavedDiscoveryService, search_id: str, reviewer: str) -> ft.Control:
    root = ScreeningControls(service, lambda: []).build()
    values = {"Saved search": search_id, "Reviewer": reviewer, "Rationale": "Methods reviewed"}
    for control in descendants(root):
        if isinstance(control, (ft.TextField, ft.Dropdown)) and control.label in values:
            control.value = values[control.label]
    saved = next(
        item
        for item in descendants(root)
        if isinstance(item, ft.Dropdown) and item.label == "Saved search"
    )
    assert isinstance(saved.on_select, FunctionType)
    saved.on_select(ft.Event(control=saved, name="select", data=search_id))
    return root


def select_candidate(root: ft.Control) -> None:
    checkbox = next(item for item in descendants(root) if isinstance(item, ft.Checkbox))
    checkbox.value = True
    assert isinstance(checkbox.on_change, FunctionType)
    checkbox.on_change(ft.Event(control=checkbox, name="change", data="true"))


@pytest.mark.parametrize("initial_revision", [0, 1])
def test_stale_displayed_review_is_refused(
    configuration: ApiConfiguration, scholar: LocalScholar, initial_revision: int
) -> None:
    service = SavedDiscoveryService(ApiRuntime(configuration).paper_database, scholar)
    search = service.save(SaveSearch(project_id="project-1", name="Concurrent", query="methods"))
    candidate = service.rerun(search.search_id).observations[0].candidate_id
    if initial_revision:
        service.review(
            ReviewRequest(
                search_id=search.search_id,
                candidate_id=candidate,
                decision="maybe",
                reviewer="Seed",
                rationale="Initial assessment",
            )
        )
    first = panel(service, search.search_id, "Alice")
    stale = panel(service, search.search_id, "Bob")
    select_candidate(first)
    select_candidate(stale)
    click(first, "Record screening")

    click(stale, "Record screening")

    reviews = service.get(search.search_id).reviews
    assert len(reviews) == initial_revision + 1
    assert reviews[-1].reviewer == "Alice"
    assert any(
        isinstance(item, ft.Text)
        and item.color == ft.Colors.RED_600
        and "reload" in (item.value or "").lower()
        for item in descendants(stale)
    )
    click(stale, "Record screening")
    assert service.get(search.search_id).reviews == reviews


@pytest.mark.parametrize(
    "refresh_action", ["Refresh saved searches", "Rerun saved query", "Record screening"]
)
def test_displayed_revision_updates_after_explicit_load_or_own_review(
    configuration: ApiConfiguration, scholar: LocalScholar, refresh_action: str
) -> None:
    service = SavedDiscoveryService(ApiRuntime(configuration).paper_database, scholar)
    search = service.save(SaveSearch(project_id="project-1", name="Current", query="methods"))
    candidate = service.rerun(search.search_id).observations[0].candidate_id
    root = panel(service, search.search_id, "Bob")
    if refresh_action == "Record screening":
        select_candidate(root)
    else:
        service.review(
            ReviewRequest(
                search_id=search.search_id,
                candidate_id=candidate,
                decision="include",
                reviewer="Alice",
                rationale="Methods fit",
            )
        )
    click(root, refresh_action)
    select_candidate(root)

    click(root, "Record screening")

    reviews = service.get(search.search_id).reviews
    assert len(reviews) == 2
    assert reviews[-1].reviewer == "Bob" and reviews[-1].expected_revision == 1
