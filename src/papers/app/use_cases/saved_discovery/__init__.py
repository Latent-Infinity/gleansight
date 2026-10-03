"""Saved searches with immutable reruns and explicit review revisions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from papers.app.use_cases.discovery import ScholarClient
from papers.app.use_cases.saved_discovery.actions import import_selection, schedule
from papers.app.use_cases.saved_discovery.claims import discovery_claim
from papers.app.use_cases.saved_discovery.provider import discover
from papers.app.use_cases.saved_discovery.reconcile import Reconciler
from papers.domain.errors import ConfigurationError, ConflictError, NotFoundError
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
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.screening import ScreeningStore


@dataclass(frozen=True, slots=True)
class SavedDiscoveryService:
    database: PiccoloDatabase
    scholar_client: ScholarClient | None = None

    @property
    def store(self) -> ScreeningStore:
        return ScreeningStore(self.database)

    def save(self, request: SaveSearch) -> SavedSearch:
        saved = SavedSearch(
            **request.model_dump(), search_id=str(uuid4()), created_at=datetime.now(UTC)
        )
        with self.store.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM projects WHERE project_id = ?", (request.project_id,)
                ).fetchone()
                is None
            ):
                raise NotFoundError(f"Project not found: {request.project_id}")
            connection.execute(
                "INSERT INTO saved_searches VALUES (?, ?, ?)",
                (saved.search_id, saved.project_id, saved.model_dump_json()),
            )
        return saved

    def list(self, project_id: str | None = None) -> tuple[SavedSearch, ...]:
        return self.store.list(project_id)

    def get(self, search_id: str) -> ScreeningDesk:
        return self.store.get(search_id)

    def rerun(
        self, search_id: str, run_id: str | None = None, *, managed: bool = False
    ) -> DiscoveryRun:
        identifier = run_id or str(uuid4())
        with self.store.transaction() as connection:
            desk = self.store.read(connection, search_id)
            existing = connection.execute(
                "SELECT document_json FROM screening_runs WHERE run_id = ?", (identifier,)
            ).fetchone()
            if existing is not None:
                run = DiscoveryRun.model_validate_json(existing[0])
                if run.search_id != search_id:
                    raise ConflictError("Run identifier belongs to a different saved search.")
                return run
        if self.scholar_client is None:
            raise ConfigurationError("Saved discovery provider is not configured.")
        with discovery_claim(self.store, search_id, identifier, managed=managed):
            results = discover(self.database, self.scholar_client, desk.search)
            with self.store.transaction() as connection:
                desk = self.store.read(connection, search_id)
                previous = tuple(item for run in desk.runs for item in run.observations)
                observations = tuple(
                    Reconciler(connection).observe(item, previous) for item in results
                )
                run = DiscoveryRun(
                    run_id=identifier,
                    search_id=search_id,
                    sequence=len(desk.runs) + 1,
                    created_at=datetime.now(UTC),
                    observations=observations,
                )
                connection.execute(
                    "INSERT INTO screening_runs VALUES (?, ?, ?, ?)",
                    (run.run_id, search_id, run.sequence, run.model_dump_json()),
                )
                return run

    def review(self, request: ReviewRequest) -> Review:
        with self.store.transaction() as connection:
            desk = self.store.read(connection, request.search_id)
            if not any(
                item.candidate_id == request.candidate_id
                for run in desk.runs
                for item in run.observations
            ):
                raise NotFoundError("Candidate has not appeared in this saved search.")
            revisions = tuple(
                item for item in desk.reviews if item.candidate_id == request.candidate_id
            )
            if request.expected_revision != len(revisions):
                raise ConflictError("Screening decision changed; reload before revising it.")
            review = Review(
                **request.model_dump(),
                review_id=str(uuid4()),
                revision=len(revisions) + 1,
                created_at=datetime.now(UTC),
            )
            connection.execute(
                "INSERT INTO screening_reviews VALUES (?, ?, ?, ?, ?)",
                (
                    review.review_id,
                    request.search_id,
                    request.candidate_id,
                    review.revision,
                    review.model_dump_json(),
                ),
            )
            return review

    def import_selected(self, request: ImportSelection) -> ImportedSelection:
        return import_selection(self.store, request)

    def schedule(self, request: ScheduleRequest) -> ScheduledSearch:
        return schedule(self.store, request)
