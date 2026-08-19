from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flet as ft

from papers.ui.screens.monitor import MonitorScreen
from papers.ui.screens.paper import PaperDetailScreen
from papers.ui.screens.query import QueryScreen
from papers.ui.screens.search import SearchScreen
from papers.ui.screens.synthesis import SynthesisScreen

if TYPE_CHECKING:
    from papers.app import use_cases


@dataclass
class UIServices:
    discover: use_cases.DiscoverCandidatesUseCase
    import_candidate: use_cases.ImportCandidateUseCase
    reject_candidate: use_cases.RejectCandidateUseCase
    search: use_cases.SearchPapersUseCase
    filter_extractions: use_cases.FilterByExtractionsUseCase
    aggregate_extractions: use_cases.AggregateExtractionsUseCase
    get_candidate: Callable[[str], dict[str, Any] | None]
    list_paper: Callable[[str], dict[str, Any] | None]
    list_runs: Callable[[str], list[dict[str, Any]]]
    list_jobs: Callable[[str | None, int], list[dict[str, Any]]]
    run_next_job: Callable[[], bool]
    enqueue_job: Callable[[str, str | None, str | None, dict[str, Any]], str]
    cancel_job: Callable[[str], None]
    delete_job: Callable[[str], None]
    bulk_delete_jobs: Callable[[list[str]], int]
    bulk_cancel_jobs: Callable[[list[str]], int]
    get_paper_markdown: Callable[[str], str | None]
    list_extractions: Callable[[str, str | None], list[Any]]
    delete_paper: Callable[[str], None]
    reset_pipeline_stage: Callable[[str, str], None]
    synthesize_from_corpus: Any
    ui_settings: dict[str, Any]


class AppState:
    ROUTES: tuple[str, ...] = ("/search", "/paper", "/monitor", "/query", "/synthesis")

    def __init__(self, services: UIServices) -> None:
        self.current_route = self.ROUTES[0]
        # Cache screen instances so state persists across navigation
        self._screens: dict[int, ft.Control] = {}
        self._services = services

    def route_for_index(self, index: int) -> str:
        if 0 <= index < len(self.ROUTES):
            return self.ROUTES[index]
        return "/unknown"

    def index_for_route(self, route: str) -> int:
        try:
            return self.ROUTES.index(route)
        except ValueError:
            return 0

    def get_screen(self, index: int) -> ft.Control:
        """Get or create a screen, caching for state persistence."""
        if index not in self._screens:
            screen_builders = {
                0: lambda: SearchScreen(self._services).build(),
                1: lambda: PaperDetailScreen(self._services).build(),
                2: lambda: MonitorScreen(self._services).build(),
                3: lambda: QueryScreen(self._services).build(),
                4: lambda: SynthesisScreen(self._services).build(),
            }
            builder = screen_builders.get(index)
            if builder:
                self._screens[index] = builder()
            else:
                self._screens[index] = ft.Text(value=f"Unknown screen: {index}")
        return self._screens[index]


class UIApp:
    def __init__(self, services: UIServices) -> None:
        self.services = services
        self.state = AppState(services)

    def build(self, page: ft.Page) -> None:
        page.title = "Gleansight"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 1200
        page.window.height = 800

        def on_nav_change(e: ft.ControlEvent) -> None:
            index = int(e.control.selected_index or 0)
            self.state.current_route = self.state.route_for_index(index)
            render()

        def pick_icon(*names: str) -> str:
            for name in names:
                icon = getattr(ft.Icons, name, None)
                if icon is not None:
                    return icon
            return getattr(ft.Icons, "HELP_OUTLINE", ft.Icons.ABC)

        nav = ft.NavigationRail(
            selected_index=self.state.index_for_route(self.state.current_route),
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=72,
            destinations=[
                ft.NavigationRailDestination(
                    icon=pick_icon("SEARCH", "SEARCH_OUTLINED", "SEARCH_SHARP"), label="Search"
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("DESCRIPTION", "DESCRIPTION_OUTLINED"), label="Paper"
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("MONITOR", "MONITOR_HEART", "MONITOR_OUTLINED"),
                    label="Monitor",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("FILTER_ALT", "FILTER_ALT_OUTLINED", "FILTER_LIST"),
                    label="Query",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("QUESTION_ANSWER", "QUESTION_ANSWER_OUTLINED", "CHAT"),
                    label="Synthesis",
                ),
            ],
            on_change=on_nav_change,
        )

        content = ft.Container(expand=True)

        def render() -> None:
            try:
                index = nav.selected_index or 0
                content.content = self.state.get_screen(index)
            except Exception as exc:
                content.content = ft.Text(value=f"UI render error: {exc}")
            page.update()

        page.add(
            ft.Row(
                [
                    nav,
                    ft.VerticalDivider(width=1),
                    content,
                ],
                expand=True,
            )
        )
        render()


def run_app(services: UIServices) -> None:
    ui = UIApp(services)
    ft.run(ui.build)
