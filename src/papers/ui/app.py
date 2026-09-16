from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flet as ft

from papers.ui.screens.acquire import AcquireScreen
from papers.ui.screens.archive import ArchiveScreen
from papers.ui.screens.card import CardScreen
from papers.ui.screens.diverge import DivergeScreen
from papers.ui.screens.gate import GateScreen
from papers.ui.screens.ground import GroundScreen
from papers.ui.screens.harvest import HarvestScreen
from papers.ui.screens.ideation import IdeationScreen
from papers.ui.screens.map import MapScreen
from papers.ui.screens.monitor import MonitorScreen
from papers.ui.screens.paper import PaperDetailScreen
from papers.ui.screens.project import ProjectScreen
from papers.ui.screens.query import QueryScreen
from papers.ui.screens.rescore import RescoreScreen
from papers.ui.screens.search import SearchScreen
from papers.ui.screens.skeleton import SkeletonScreen
from papers.ui.screens.synthesis import SynthesisScreen
from papers.ui.screens.tau import TauScreen

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
    map_snapshot: Callable[..., dict[str, Any]] | None = None
    list_archive_elites: Callable[[], list[dict[str, Any]]] | None = None
    get_frontier_card: Callable[[str], dict[str, Any] | None] | None = None
    harvest_records: Callable[..., dict[str, Any]] | None = None
    diverge_candidate: Callable[..., dict[str, Any]] | None = None
    ground_candidate: Callable[..., dict[str, Any]] | None = None
    gate_candidate: Callable[..., dict[str, Any]] | None = None
    project_records: Callable[..., dict[str, Any]] | None = None
    approve_digest: Callable[..., dict[str, Any]] | None = None
    acquire_corpus: Callable[..., dict[str, Any]] | None = None
    run_paper_jobs: Callable[..., dict[str, Any]] | None = None
    rescore_card: Callable[..., dict[str, Any]] | None = None
    tau_command: Callable[..., dict[str, Any]] | None = None
    run_skeleton_loop: Callable[..., dict[str, Any]] | None = None
    ideate_project: Callable[..., dict[str, Any]] | None = None
    plan_idea: Callable[..., dict[str, Any]] | None = None
    rank_archive: Callable[..., dict[str, Any]] | None = None


class AppState:
    ROUTES: tuple[str, ...] = (
        "/search",
        "/paper",
        "/monitor",
        "/query",
        "/synthesis",
        "/harvest",
        "/map",
        "/diverge",
        "/ground",
        "/gate",
        "/project",
        "/acquire",
        "/rescore",
        "/tau",
        "/skeleton",
        "/archive",
        "/card",
        "/ideation",
    )

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
                5: lambda: HarvestScreen(self._services).build(),
                6: lambda: MapScreen(self._services).build(),
                7: lambda: DivergeScreen(self._services).build(),
                8: lambda: GroundScreen(self._services).build(),
                9: lambda: GateScreen(self._services).build(),
                10: lambda: ProjectScreen(self._services).build(),
                11: lambda: AcquireScreen(self._services).build(),
                12: lambda: RescoreScreen(self._services).build(),
                13: lambda: TauScreen(self._services).build(),
                14: lambda: SkeletonScreen(self._services).build(),
                15: lambda: ArchiveScreen(self._services).build(),
                16: lambda: CardScreen(self._services).build(),
                17: lambda: IdeationScreen(self._services).build(),
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
            height=len(self.state.ROUTES) * 72,
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
                ft.NavigationRailDestination(
                    icon=pick_icon("AGRICULTURE", "DOWNLOAD", "INPUT"),
                    label="Harvest",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("MAP", "MAP_OUTLINED", "PUBLIC"),
                    label="Map",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("ALT_ROUTE", "CALL_SPLIT", "ACCOUNT_TREE"),
                    label="Diverge",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("TRAVEL_EXPLORE", "FIND_IN_PAGE", "SEARCH"),
                    label="Ground",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("FACT_CHECK", "RULE", "GAVEL"),
                    label="Gate",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("UPLOAD_FILE", "NOTE_ADD", "POST_ADD"),
                    label="Project",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("CLOUD_DOWNLOAD", "GET_APP", "DOWNLOAD"),
                    label="Acquire",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("REFRESH", "REPLAY", "UPDATE"),
                    label="Rescore",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("SCIENCE", "ANALYTICS", "INSIGHTS"),
                    label="Tau",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("BOLT", "FLASH_ON", "PLAY_ARROW"),
                    label="Skeleton",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("ARCHIVE", "ARCHIVE_OUTLINED", "INVENTORY_2"),
                    label="Archive",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("BADGE", "ARTICLE", "DESCRIPTION"),
                    label="Card",
                ),
                ft.NavigationRailDestination(
                    icon=pick_icon("LIGHTBULB", "TIPS_AND_UPDATES", "SCIENCE"),
                    label="Ideation",
                ),
            ],
            on_change=on_nav_change,
        )

        content = ft.Container(expand=True)
        nav_scroller = ft.Column(
            [nav],
            height=max(float(page.height or page.window.height or 800) - 20, 0),
            scroll=ft.ScrollMode.AUTO,
        )

        def resize_navigation(_: ft.ControlEvent) -> None:
            nav_scroller.height = max(float(page.height or page.window.height or 800) - 20, 0)
            nav_scroller.update()

        page.on_resize = resize_navigation

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
                    nav_scroller,
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
