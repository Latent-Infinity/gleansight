from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation
from gleansight.api.papers.common import Page, Query, database, one, page
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.discovery import (
    DiscoverCandidatesUseCase,
    ImportCandidateUseCase,
    RejectCandidateUseCase,
)
from papers.infra.piccolo.stores import (
    PiccoloAtomicCandidateImport,
    PiccoloCandidateStore,
    PiccoloJobQueue,
    PiccoloPaperStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)
from papers.infra.scholar_s2.adapter import build_s2_client


class CandidateId(Request):
    candidate_id: Identifier


class CandidateImport(CandidateId):
    project_ids: Annotated[list[Identifier], Field(max_length=100)] = []
    tag_ids: Annotated[list[Identifier], Field(max_length=100)] = []


class CandidatePage(Page):
    status: Literal["all", "pending", "imported", "rejected"] = "all"


class DiscoveryFilters(Request):
    year_min: int | None = None
    year_max: int | None = None
    publication_types: list[Identifier] | None = None
    fields_of_study: list[Identifier] | None = None
    venue: list[Identifier] | None = None
    min_citation_count: Annotated[int, Field(ge=0)] | None = None
    open_access_pdf: bool | None = None
    publication_date_or_year: str | None = None


class Discover(Request):
    query: Identifier
    filters: DiscoveryFilters = Field(default_factory=DiscoveryFilters)
    max_results: Annotated[int, Field(ge=1, le=1000)] = 50
    page_size: Annotated[int, Field(ge=1, le=100)] = 100
    offset: Annotated[int, Field(ge=0)] = 0


def discover(runtime: ApiRuntime, request: Discover) -> JsonValue:
    database(runtime)
    settings = runtime.settings.scholar
    client = build_s2_client(
        api_key=settings.api_key or None, rate_limit_per_second=settings.rate_limit_per_second
    )
    identifiers = DiscoverCandidatesUseCase(client, PiccoloCandidateStore()).discover(
        query=request.query,
        filters=request.filters.model_dump(exclude_none=True),
        max_results=request.max_results,
        page_size=request.page_size,
        offset=request.offset,
    )
    return {"candidate_ids": list(identifiers)}


def list_candidates(runtime: ApiRuntime, request: CandidatePage) -> JsonValue:
    predicates = {
        "all": "1=1",
        "pending": "imported_paper_id IS NULL AND rejected_at IS NULL",
        "imported": "imported_paper_id IS NOT NULL",
        "rejected": "rejected_at IS NOT NULL",
    }
    return page(
        runtime,
        Query(
            "SELECT * FROM candidates WHERE "
            + predicates[request.status]
            + " ORDER BY candidate_id"
        ),
        request,
    )


def import_candidate(runtime: ApiRuntime, request: CandidateImport) -> JsonValue:
    database(runtime)
    use_case = ImportCandidateUseCase(
        candidate_store=PiccoloCandidateStore(),
        paper_store=PiccoloPaperStore(),
        job_queue=PiccoloJobQueue(),
        project_store=PiccoloProjectStore(),
        tag_store=PiccoloTagStore(),
        atomic_candidate_import=PiccoloAtomicCandidateImport(),
    )
    return {
        "paper_id": use_case.import_candidate(
            request.candidate_id, project_ids=request.project_ids, tag_ids=request.tag_ids
        )
    }


def reject(runtime: ApiRuntime, request: CandidateId) -> JsonValue:
    database(runtime)
    RejectCandidateUseCase(PiccoloCandidateStore()).reject(request.candidate_id)
    return {"rejected": True}


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.candidates.discover",
            "Discover and retain scholarly candidates.",
            Discover,
            discover,
            ("write", "external"),
        ),
        Operation(
            "papers.candidates.list",
            "List candidates with pagination.",
            CandidatePage,
            list_candidates,
        ),
        Operation(
            "papers.candidates.get",
            "Get a discovered candidate.",
            CandidateId,
            lambda r, q: one(
                r, Query("SELECT * FROM candidates WHERE candidate_id = ?", (q.candidate_id,))
            ),
        ),
        Operation(
            "papers.candidates.import",
            "Import a candidate atomically with memberships and download job.",
            CandidateImport,
            import_candidate,
            ("write",),
        ),
        Operation(
            "papers.candidates.reject",
            "Reject an unimported candidate.",
            CandidateId,
            reject,
            ("write",),
        ),
    )
