from __future__ import annotations

from dataclasses import dataclass

from papers.ui.app import UIApp, UIServices


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
    get_paper_markdown: object
    ui_settings: object


def test_app_builds_navigation() -> None:
    services = FakeServices(
        discover=object(),
        import_candidate=object(),
        reject_candidate=object(),
        search=object(),
        filter_extractions=object(),
        aggregate_extractions=object(),
        get_candidate=lambda _: None,
        list_paper=lambda _: None,
        list_runs=lambda _: [],
        list_jobs=lambda: [],
        get_paper_markdown=lambda _: None,
        ui_settings={},
    )
    app = UIApp(services)

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

    page = FakePage()
    app.build(page)

    assert page.controls
