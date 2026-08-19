from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import flet as ft

from papers.ui.screens.search import SearchScreen


@dataclass
class FakeDiscover:
    def discover(
        self,
        *,
        query: str,
        filters: dict,
        max_results: int,
        offset: int = 0,
    ):
        return ["cand-1"]


@dataclass
class FakeImport:
    def import_candidate(self, *, candidate_id: str):
        return "paper-1"


@dataclass
class FakeReject:
    def reject(self, *, candidate_id: str):
        return None


@dataclass
class FakeCandidateStore:
    def get_candidate(self, candidate_id: str):
        return {
            "candidate_id": candidate_id,
            "title": "Example Paper",
            "year": 2024,
            "venue": "TestConf",
            "authors_json": "[]",
            "abstract": "Abstract",
            "external_ids_json": '{"ArXiv": "2301.00001"}',
        }


def test_search_screen_builds() -> None:
    services = type(
        "Services",
        (),
        {
            "discover": FakeDiscover(),
            "import_candidate": FakeImport(),
            "reject_candidate": FakeReject(),
            "get_candidate": FakeCandidateStore().get_candidate,
        },
    )()
    screen = SearchScreen(services)

    control = screen.build()

    assert isinstance(control, ft.Control)


def test_search_screen_uses_require_open_access_from_settings() -> None:
    """Test that open access switch uses require_open_access from ui_settings."""
    services = type(
        "Services",
        (),
        {
            "discover": FakeDiscover(),
            "import_candidate": FakeImport(),
            "reject_candidate": FakeReject(),
            "get_candidate": FakeCandidateStore().get_candidate,
            "ui_settings": {"require_open_access": True},
        },
    )()
    screen = SearchScreen(services)

    control = screen.build()

    # The control is a Column; find the Switch within it
    assert isinstance(control, ft.Column)

    # The switch should be in the filters ExpansionPanelList
    # Find all Switch controls recursively
    def find_switches(ctrl: ft.Control) -> list[ft.Switch]:
        switches = []
        if isinstance(ctrl, ft.Switch):
            switches.append(ctrl)
        if hasattr(ctrl, "controls"):
            for child in ctrl.controls:
                switches.extend(find_switches(child))
        if hasattr(ctrl, "content"):
            if ctrl.content:
                switches.extend(find_switches(ctrl.content))
        return switches

    switches = find_switches(control)
    # Find the open access switch
    open_access_switches = [s for s in switches if "Open access" in (s.label or "")]
    assert len(open_access_switches) == 1
    assert open_access_switches[0].value is True


def _find_all(root: ft.Control, control_type: type) -> list:
    """Recursively find all controls of a given type in the tree."""
    found = []
    if isinstance(root, control_type):
        found.append(root)
    for attr in ("controls", "content"):
        child = getattr(root, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for c in child:
                if isinstance(c, ft.Control):
                    found.extend(_find_all(c, control_type))
        elif isinstance(child, ft.Control):
            found.extend(_find_all(child, control_type))
    return found


def _button_label(button: ft.Control) -> str | None:
    text = getattr(button, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(button, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, ft.Text):
        return content.value
    return None


def _build_search_services(**overrides):
    """Build a minimal services object for SearchScreen tests.

    Sets attributes on an *instance* (not the class) so that lambdas/functions
    are stored in ``__dict__`` and bypass the descriptor protocol — otherwise
    ``type("S", (), {"fn": lambda x: x})().fn`` would bind the lambda to the
    instance, adding an unwanted ``self`` argument.
    """
    services = type("Services", (), {})()
    services.discover = FakeDiscover()
    services.import_candidate = FakeImport()
    services.reject_candidate = FakeReject()
    services.get_candidate = FakeCandidateStore().get_candidate
    services.list_paper = lambda pid: None
    services.list_jobs = lambda status, limit: []
    services.enqueue_job = lambda t, p, r, pl: "job-id"
    services.ui_settings = {}
    for key, val in overrides.items():
        setattr(services, key, val)
    return services


def _trigger_search(col: ft.Column) -> ft.ListView:
    """Trigger a search on a built SearchScreen Column, return the ListView."""
    from unittest.mock import patch

    listviews = _find_all(col, ft.ListView)
    assert listviews, "No ListView found in control tree"
    results_view = listviews[0]

    # Find query TextField
    textfields = _find_all(col, ft.TextField)
    query_input = next((tf for tf in textfields if tf.label == "Search"), None)
    assert query_input is not None, "No Search TextField found"

    query_input.value = "test"
    # Patch Control.update at the class level so unmounted controls don't raise
    with patch.object(ft.Control, "update", return_value=None):
        query_input.on_submit(MagicMock())

    return results_view


def test_import_click_does_not_call_page_update() -> None:
    """Import should update individual controls, not page.update() which resets scroll."""
    from unittest.mock import patch

    services = _build_search_services()
    screen = SearchScreen(services)
    col = screen.build()

    results_view = _trigger_search(col)
    assert len(results_view.controls) == 1, "Expected one result card"

    card = results_view.controls[0]
    # Find the Import button
    buttons = _find_all(card, ft.Button)
    import_btn = next((b for b in buttons if _button_label(b) == "Import"), None)
    assert import_btn is not None, "No Import button found"

    # Create a mock event with a mock page
    mock_page = MagicMock()
    mock_event = MagicMock()
    mock_event.page = mock_page
    mock_event.control.page = mock_page

    # Patch Control.update so per-control updates don't raise on unmounted controls
    with patch.object(ft.Control, "update", return_value=None):
        import_btn.on_click(mock_event)

    # page.update() must NOT be called (it resets scroll position)
    mock_page.update.assert_not_called()


def test_reject_click_does_not_call_page_update() -> None:
    """Reject should update individual controls, not page.update() which resets scroll."""
    from unittest.mock import patch

    services = _build_search_services()
    screen = SearchScreen(services)
    col = screen.build()

    results_view = _trigger_search(col)
    assert len(results_view.controls) == 1

    card = results_view.controls[0]
    buttons = _find_all(card, ft.OutlinedButton)
    reject_btn = next((b for b in buttons if b.content == "Reject"), None)
    assert reject_btn is not None, "No Reject button found"

    mock_page = MagicMock()
    mock_event = MagicMock()
    mock_event.page = mock_page
    mock_event.control.page = mock_page

    with patch.object(ft.Control, "update", return_value=None):
        reject_btn.on_click(mock_event)

    mock_page.update.assert_not_called()


def test_search_pagination_loads_more() -> None:
    """Load more advances the discovery offset and appends the next page."""
    from unittest.mock import patch

    offsets: list[int] = []

    class PaginatingDiscover:
        def discover(
            self,
            *,
            query: str,
            filters: dict,
            max_results: int,
            offset: int = 0,
        ) -> list[str]:
            offsets.append(offset)
            return [f"cand-{offset + 1}"]

    services = _build_search_services(discover=PaginatingDiscover())
    services.ui_settings = {"search_max_results": 1}
    screen = SearchScreen(services)
    col = screen.build()

    with patch.object(ft.Control, "update", return_value=None):
        results_view = _trigger_search(col)
        assert len(results_view.controls) == 1

        buttons = _find_all(col, ft.Button)
        load_more = next(
            (button for button in buttons if "load more" in (_button_label(button) or "").lower()),
            None,
        )
        assert load_more is not None
        assert load_more.visible
        load_more.on_click(MagicMock())

    assert offsets == [0, 1]
    assert len(results_view.controls) == 2


def test_bulk_import_selected() -> None:
    """Selecting candidates and clicking 'Import selected' imports them all."""
    from unittest.mock import patch

    import_calls = []

    class TrackingImport:
        def import_candidate(self, *, candidate_id: str):
            import_calls.append(candidate_id)
            return "paper-1"

    services = _build_search_services(import_candidate=TrackingImport())
    screen = SearchScreen(services)
    col = screen.build()

    with patch.object(ft.Control, "update", return_value=None):
        results_view = _trigger_search(col)
        assert results_view.controls, "Need at least one result card"

        # Find the checkbox and select it
        checkboxes = _find_all(col, ft.Checkbox)
        assert checkboxes, "No checkboxes found"
        checkboxes[0].value = True
        if checkboxes[0].on_change:
            checkboxes[0].on_change(MagicMock())

        # Find and click "Import selected"
        buttons = _find_all(col, ft.Button)
        import_selected_btn = next(
            (b for b in buttons if "import selected" in (_button_label(b) or "").lower()),
            None,
        )
        assert import_selected_btn is not None, "No 'Import selected' button found"
        import_selected_btn.on_click(MagicMock())
        assert len(import_calls) >= 1, "Should have imported at least one candidate"


def test_advanced_filters_applied() -> None:
    """Year filters are passed through to the discover use case."""
    from unittest.mock import patch

    captured_kwargs = {}

    class CapturingDiscover:
        def discover(
            self,
            *,
            query: str,
            filters: dict,
            max_results: int,
            offset: int = 0,
        ):
            captured_kwargs.update(filters)
            return ["cand-1"]

    services = _build_search_services(discover=CapturingDiscover())
    screen = SearchScreen(services)
    col = screen.build()

    # Find filter fields
    textfields = _find_all(col, ft.TextField)
    year_from = next((tf for tf in textfields if tf.label == "Year from"), None)
    year_to = next((tf for tf in textfields if tf.label == "Year to"), None)
    assert year_from is not None, "No 'Year from' field found"
    assert year_to is not None, "No 'Year to' field found"

    year_from.value = "2020"
    year_to.value = "2024"

    with patch.object(ft.Control, "update", return_value=None):
        # Trigger search via submit
        query_input = next((tf for tf in textfields if tf.label == "Search"), None)
        assert query_input is not None
        query_input.value = "test"
        query_input.on_submit(MagicMock())

    assert captured_kwargs.get("year_min") == 2020
    assert captured_kwargs.get("year_max") == 2024
