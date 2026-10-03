"""Durable saved-search, observation and attributed screening contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from papers.domain.errors import ValidationError

Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
Identity = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[\w.-]+$")]


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SearchFilters(Record):
    year_min: int | None = None
    year_max: int | None = None
    publication_types: tuple[str, ...] | None = None
    fields_of_study: tuple[str, ...] | None = None
    venue: tuple[str, ...] | None = None
    min_citation_count: Annotated[int, Field(ge=0)] | None = None
    open_access_pdf: bool | None = None
    publication_date_or_year: str | None = None

    @model_validator(mode="after")
    def ordered_years(self) -> SearchFilters:
        if (
            self.year_min is not None
            and self.year_max is not None
            and self.year_min > self.year_max
        ):
            raise ValidationError("Search year range is reversed.")
        return self


class SaveSearch(Record):
    project_id: Identity
    name: Text
    query: Text
    filters: SearchFilters = Field(default_factory=SearchFilters)
    provider: Literal["semantic_scholar"] = "semantic_scholar"
    provider_ref: Literal["default"] = "default"
    max_results: Annotated[int, Field(ge=1, le=1000)] = 50


class SavedSearch(SaveSearch):
    search_id: Identity
    created_at: datetime


class SearchResult(Record):
    source_paper_id: Text
    title: Text
    year: int | None = None
    venue: str | None = None
    authors: tuple[str, ...] = ()
    abstract: str | None = None
    external_ids: dict[str, str] | None = None


class Observation(Record):
    candidate_id: Identity
    source: str
    source_paper_id: str
    doi: str | None
    metadata: SearchResult
    metadata_sha256: str
    delta: Literal["new", "seen", "metadata_changed"]


class DiscoveryRun(Record):
    run_id: Identity
    search_id: Identity
    sequence: int
    created_at: datetime
    observations: tuple[Observation, ...]


class ReviewRequest(Record):
    search_id: Identity
    candidate_id: Identity
    decision: Literal["include", "exclude", "maybe"]
    reviewer: Text
    rationale: Text
    expected_revision: Annotated[int, Field(ge=0)] = 0


class Review(ReviewRequest):
    review_id: Identity
    revision: int
    created_at: datetime


class ScreeningDesk(Record):
    search: SavedSearch
    runs: tuple[DiscoveryRun, ...]
    reviews: tuple[Review, ...]


class ImportSelection(Record):
    search_id: Identity
    candidate_ids: Annotated[tuple[Identity, ...], Field(min_length=1, max_length=100)]
    tag_ids: tuple[Identity, ...] = ()


class ImportedSelection(Record):
    paper_ids: tuple[str, ...]


class ScheduleRequest(Record):
    search_id: Identity
    first_run: datetime
    interval_minutes: Annotated[int, Field(ge=1, le=525600)] = 1440
    runs: Annotated[int, Field(ge=1, le=12)] = 1
    request_id: Identity


class ScheduledSearch(Record):
    request: ScheduleRequest
    job_ids: tuple[str, ...]
