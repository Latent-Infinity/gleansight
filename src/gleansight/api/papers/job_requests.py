from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from gleansight.api.models import Identifier, Request
from gleansight.api.papers.candidates import Discover
from gleansight.api.papers.common import Page
from papers.domain.models import JobStatus


class JobId(Request):
    job_id: Identifier


class JobIds(Request):
    job_ids: Annotated[list[Identifier], Field(min_length=1, max_length=1000)]


class JobPage(Page):
    status: JobStatus | None = None
    paper_id: Identifier | None = None


class Attempts(Request):
    max_attempts: Annotated[int, Field(ge=1, le=100)] = 3


class DownloadPayload(Attempts):
    source_path: Identifier | None = None
    external_ids: dict[str, Identifier] | None = None


class AnalyzePayload(Attempts):
    prompt_version_id: Identifier
    profile_id: Identifier
    model_name: Identifier
    timeout_s: Annotated[int, Field(ge=1, le=600)] | None = None


class DownloadJob(Request):
    type: Literal["download"]
    paper_id: Identifier
    payload: DownloadPayload = Field(default_factory=DownloadPayload)


class ConvertJob(Request):
    type: Literal["convert"]
    paper_id: Identifier
    payload: DownloadPayload = Field(default_factory=DownloadPayload)


class EmbedJob(Request):
    type: Literal["embed"]
    paper_id: Identifier
    payload: Attempts = Field(default_factory=Attempts)


class AnalyzeJob(Request):
    type: Literal["analyze"]
    paper_id: Identifier
    run_id: Identifier
    payload: AnalyzePayload


class DiscoverPayload(Discover):
    offset: Literal[0] = 0
    max_attempts: Annotated[int, Field(ge=1, le=100)] = 3


class DiscoverJob(Request):
    type: Literal["discover"]
    payload: DiscoverPayload


type QueuedJob = Annotated[
    DownloadJob | ConvertJob | EmbedJob | AnalyzeJob | DiscoverJob,
    Field(discriminator="type"),
]


class EnqueueJob(Request):
    job: QueuedJob


class RunBounded(Request):
    max_jobs: Annotated[int, Field(ge=1, le=1000)] = 1


class Recover(Request):
    stuck_after_seconds: Annotated[int, Field(ge=1)] = 3600
