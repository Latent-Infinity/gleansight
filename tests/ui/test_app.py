from __future__ import annotations

from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.app import UIApp, UIServices, run_app
from tests.ui.fake_services import complete_ui_services


def _build_services() -> UIServices:
    return complete_ui_services()


class FakePage(ft.Page):
    def __init__(self) -> None:
        super().__init__(sess=MagicMock())
        self.controls: list[ft.Control] = []
        self.height = 800
        self.on_resize = None
        self.title = ""
        self.theme_mode = None
        self.window.width = 0
        self.window.height = 0

    def add(self, *controls: ft.Control) -> None:
        self.controls.extend(controls)

    def update(self, *controls: ft.Control) -> None:
        return None


def test_app_builds_navigation() -> None:
    services = _build_services()
    app = UIApp(services)

    page = FakePage()
    app.build(page)

    assert page.controls


def test_run_app_uses_current_flet_launcher() -> None:
    services = _build_services()

    with patch("papers.ui.app.ft.run") as run:
        run_app(services)

    run.assert_called_once()
    assert callable(run.call_args.args[0])


def test_app_state_caches_screen_instances() -> None:
    services = _build_services()
    app = UIApp(services)

    first = app.state.get_screen(0)
    second = app.state.get_screen(0)
    unknown = app.state.get_screen(99)

    assert first is second
    assert isinstance(unknown, ft.Text)
    assert app.state.route_for_index(2) == "/monitor"
    assert app.state.index_for_route("/query") == 3
    assert app.state.route_for_index(5) == "/harvest"
    assert app.state.route_for_index(6) == "/map"
    assert app.state.route_for_index(7) == "/diverge"
    assert app.state.route_for_index(8) == "/ground"
    assert app.state.route_for_index(9) == "/gate"
    assert app.state.route_for_index(10) == "/project"
    assert app.state.route_for_index(11) == "/acquire"
    assert app.state.route_for_index(12) == "/rescore"
    assert app.state.route_for_index(13) == "/tau"
    assert app.state.route_for_index(14) == "/skeleton"
    assert app.state.route_for_index(15) == "/archive"
    assert app.state.route_for_index(16) == "/card"
    assert app.state.index_for_route("/map") == 6


def test_navigation_updates_route_and_screen() -> None:
    services = _build_services()
    app = UIApp(services)
    page = FakePage()
    app.build(page)

    root_row = page.controls[0]
    assert isinstance(root_row, ft.Row)
    nav_scroller = root_row.controls[0]
    assert isinstance(nav_scroller, ft.Column)
    assert nav_scroller.height == 780
    nav = nav_scroller.controls[0]
    content = root_row.controls[2]
    assert isinstance(nav, ft.NavigationRail)
    assert isinstance(content, ft.Container)

    initial_content = content.content
    nav.selected_index = 1
    on_change = getattr(nav, "on_change")
    assert callable(on_change)
    on_change(MagicMock(control=nav))

    assert app.state.current_route == "/paper"
    assert content.content is app.state.get_screen(1)
    assert content.content is not initial_content


def test_navigation_exposes_every_registered_workflow_label() -> None:
    app = UIApp(_build_services())
    page = FakePage()
    app.build(page)
    root_row = page.controls[0]
    assert isinstance(root_row, ft.Row)
    nav_scroller = root_row.controls[0]

    assert isinstance(nav_scroller, ft.Column)
    assert nav_scroller.scroll is ft.ScrollMode.ALWAYS
    nav = nav_scroller.controls[0]
    assert isinstance(nav, ft.NavigationRail)
    assert nav.height == len(app.state.ROUTES) * 72
    assert [destination.label for destination in nav.destinations] == [
        "Search",
        "Paper",
        "Monitor",
        "Query",
        "Synthesis",
        "Harvest",
        "Map",
        "Diverge",
        "Ground",
        "Gate",
        "Project",
        "Acquire",
        "Rescore",
        "Tau",
        "Skeleton",
        "Archive",
        "Card",
        "Ideation",
    ]
    assert app.state.route_for_index(17) == "/ideation"

    page.height = 600
    assert page.on_resize is not None
    with patch.object(ft.Control, "update", return_value=None):
        on_resize = getattr(page, "on_resize")
        assert callable(on_resize)
        on_resize(MagicMock())
    assert nav_scroller.height == 580
