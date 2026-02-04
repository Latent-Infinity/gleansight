from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import flet as ft

from papers.ui.screens.monitor import MonitorScreen
from papers.ui.screens.paper import PaperDetailScreen
from papers.ui.screens.query import QueryScreen
from papers.ui.screens.search import SearchScreen

if TYPE_CHECKING:
    from papers.app import use_cases


@dataclass
class UIServices:
    discover: "use_cases.DiscoverCandidatesUseCase"
    import_candidate: "use_cases.ImportCandidateUseCase"
    reject_candidate: "use_cases.RejectCandidateUseCase"
    search: "use_cases.SearchPapersUseCase"
    filter_extractions: "use_cases.FilterByExtractionsUseCase"
    aggregate_extractions: "use_cases.AggregateExtractionsUseCase"
    get_candidate: Callable[[str], dict[str, Any] | None]
    list_paper: Callable[[str], dict[str, Any] | None]
    list_runs: Callable[[str], list[dict[str, Any]]]
    list_jobs: Callable[[], list[dict[str, Any]]]
    get_paper_markdown: Callable[[str], str | None]
    ui_settings: dict[str, Any]


class AppState:
    def __init__(self, services: "UIServices") -> None:
        self.current_route = "/search"
        # Cache screen instances so state persists across navigation
        self._screens: dict[int, ft.Control] = {}
        self._services = services

    def get_screen(self, index: int) -> ft.Control:
        """Get or create a screen, caching for state persistence."""
        if index not in self._screens:
            screen_builders = {
                0: lambda: SearchScreen(self._services).build(),
                1: lambda: PaperDetailScreen(self._services).build(),
                2: lambda: MonitorScreen(self._services).build(),
                3: lambda: QueryScreen(self._services).build(),
            }
            builder = screen_builders.get(index)
            if builder:
                self._screens[index] = builder()
            else:
                self._screens[index] = ft.Text(f"Unknown screen: {index}")
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
            self.state.current_route = str(e.control.selected_index or 0)
            render()

        def pick_icon(*names: str) -> str:
            for name in names:
                icon = getattr(ft.Icons, name, None)
                if icon is not None:
                    return icon
            return getattr(ft.Icons, "HELP_OUTLINE", ft.Icons.ABC)

        nav = ft.NavigationRail(
            selected_index=0,
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
            ],
            on_change=on_nav_change,
        )

        content = ft.Container(expand=True)

        def render() -> None:
            try:
                index = nav.selected_index or 0
                content.content = self.state.get_screen(index)
            except Exception as exc:
                content.content = ft.Text(f"UI render error: {exc}")
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
    ft.app(target=ui.build)
