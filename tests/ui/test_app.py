from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.app import UIApp, UIServices, run_app


@dataclass
class FakeServices(UIServices):
    discover: object
    import_candidate: object
    reject_candidate: object
    search: object
    filter_extractions: object
    aggregate_extractions: object
    get_candidate: object
    list_paper: object
    list_runs: object
    list_jobs: object
    run_next_job: object
    enqueue_job: object
    cancel_job: object
    delete_job: object
    bulk_delete_jobs: object
    bulk_cancel_jobs: object
    get_paper_markdown: object
    list_extractions: object
    delete_paper: object
    reset_pipeline_stage: object
    synthesize_from_corpus: object
    ui_settings: object


def _build_services() -> FakeServices:
    return FakeServices(
        discover=object(),
        import_candidate=object(),
        reject_candidate=object(),
        search=object(),
        filter_extractions=object(),
        aggregate_extractions=object(),
        get_candidate=lambda _: None,
        list_paper=lambda _: None,
        list_runs=lambda _: [],
        list_jobs=lambda _status, _limit: [],
        run_next_job=lambda: False,
        enqueue_job=lambda _t, _p, _r, _pl: "job-id",
        cancel_job=lambda _: None,
        delete_job=lambda _: None,
        bulk_delete_jobs=lambda _ids: 0,
        bulk_cancel_jobs=lambda _ids: 0,
        get_paper_markdown=lambda _: None,
        list_extractions=lambda _pid, _pv=None: [],
        delete_paper=lambda _: None,
        reset_pipeline_stage=lambda _pid, _stage: None,
        synthesize_from_corpus=object(),
        ui_settings={},
    )


class FakeWindow:
    def __init__(self) -> None:
        self.width = 0
        self.height = 0


class FakePage:
    def __init__(self) -> None:
        self.controls: list = []
        self.title = ""
        self.theme_mode = None
        self.window = FakeWindow()

    def add(self, *controls) -> None:  # noqa: ANN001 - test stub
        self.controls.extend(controls)

    def update(self) -> None:  # noqa: ANN001 - test stub
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


def test_navigation_updates_route_and_screen() -> None:
    services = _build_services()
    app = UIApp(services)
    page = FakePage()
    app.build(page)

    root_row = page.controls[0]
    assert isinstance(root_row, ft.Row)
    nav = root_row.controls[0]
    content = root_row.controls[2]
    assert isinstance(nav, ft.NavigationRail)
    assert isinstance(content, ft.Container)

    initial_content = content.content
    nav.selected_index = 1
    nav.on_change(MagicMock(control=nav))

    assert app.state.current_route == "/paper"
    assert content.content is app.state.get_screen(1)
    assert content.content is not initial_content
