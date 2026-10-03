"""Narrow desktop saved-discovery surface, composed from the existing provider and database."""

from typing import Protocol, TypedDict

from pydantic import BaseModel, ConfigDict

from papers.app.composition_root import AppContainer
from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.domain.screening import (
    DiscoveryRun,
    ImportedSelection,
    ImportSelection,
    Review,
    ReviewRequest,
    SavedSearch,
    SaveSearch,
    ScheduledSearch,
    ScheduleRequest,
    ScreeningDesk,
)


class ProjectOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    project_id: str
    name: str


class ScreeningService(Protocol):
    def save(self, request: SaveSearch) -> SavedSearch: ...
    def list(self, project_id: str | None = None) -> tuple[SavedSearch, ...]: ...
    def get(self, search_id: str) -> ScreeningDesk: ...
    def rerun(self, search_id: str, run_id: str | None = None) -> DiscoveryRun: ...
    def review(self, request: ReviewRequest) -> Review: ...
    def import_selected(self, request: ImportSelection) -> ImportedSelection: ...
    def schedule(self, request: ScheduleRequest) -> ScheduledSearch: ...


class ScreeningServices(TypedDict):
    screening: ScreeningService


def build_screening_services(base: AppContainer) -> ScreeningServices:
    return ScreeningServices(
        screening=SavedDiscoveryService(base.db, base.handler_context.scholar_client)
    )
