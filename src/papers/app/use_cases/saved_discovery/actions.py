"""Import explicitly included candidates and enqueue bounded future discovery runs."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from papers.app.use_cases.discovery import ImportCandidateUseCase
from papers.domain.errors import ConflictError, ValidationError
from papers.domain.screening import (
    ImportedSelection,
    ImportSelection,
    ScheduledSearch,
    ScheduleRequest,
)
from papers.infra.piccolo.stores import (
    PiccoloAtomicCandidateImport,
    PiccoloCandidateStore,
    PiccoloJobQueue,
    PiccoloPaperStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)
from papers.infra.screening import ScreeningStore


def import_selection(store: ScreeningStore, request: ImportSelection) -> ImportedSelection:
    desk = store.get(request.search_id)
    latest = {review.candidate_id: review for review in desk.reviews}
    identifiers = tuple(dict.fromkeys(request.candidate_ids))
    if any(
        identifier not in latest or latest[identifier].decision != "include"
        for identifier in identifiers
    ):
        raise ValidationError("Only candidates with a current include decision may be imported.")
    with store.database.temporary_table_bindings():
        importer = ImportCandidateUseCase(
            candidate_store=PiccoloCandidateStore(),
            paper_store=PiccoloPaperStore(),
            job_queue=PiccoloJobQueue(),
            project_store=PiccoloProjectStore(),
            tag_store=PiccoloTagStore(),
            atomic_candidate_import=PiccoloAtomicCandidateImport(),
        )
        return ImportedSelection(
            paper_ids=tuple(
                importer.import_candidate(
                    identifier, project_ids=[desk.search.project_id], tag_ids=list(request.tag_ids)
                )
                for identifier in identifiers
            )
        )


def schedule(store: ScreeningStore, request: ScheduleRequest) -> ScheduledSearch:
    with store.transaction() as connection:
        store.read(connection, request.search_id)
        existing = connection.execute(
            "SELECT document_json FROM screening_schedules WHERE request_id = ?",
            (request.request_id,),
        ).fetchone()
        if existing is not None:
            prior = ScheduledSearch.model_validate_json(existing[0])
            if prior.request.model_dump(mode="json") != request.model_dump(mode="json"):
                raise ConflictError("Schedule request identifier already has different settings.")
            return prior
        now = datetime.now(UTC)
        if request.first_run.tzinfo is None or request.first_run <= now:
            raise ValidationError("First scheduled run must be a future timezone-aware time.")
        jobs: list[str] = []
        for index in range(request.runs):
            identifier = str(uuid4())
            due = request.first_run + timedelta(minutes=request.interval_minutes * index)
            connection.execute(
                "INSERT INTO jobs(job_id,type,status,paper_id,run_id,payload_json,"
                "attempts,max_attempts,"
                "run_after,created_at,updated_at) VALUES (?, "
                "'discover','queued',NULL,NULL,?,0,3,?,?,?)",
                (
                    identifier,
                    json.dumps({"saved_search_id": request.search_id}),
                    due.astimezone(UTC).isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            jobs.append(identifier)
        result = ScheduledSearch(request=request, job_ids=tuple(jobs))
        connection.execute(
            "INSERT INTO screening_schedules VALUES (?, ?)",
            (request.request_id, result.model_dump_json()),
        )
        return result
