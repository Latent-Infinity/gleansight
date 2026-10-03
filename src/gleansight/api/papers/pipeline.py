from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.common import PaperId, Query, database, one, require_paper
from gleansight.api.papers.query import ProjectFilter
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.analysis import (
    AnalyzeProjectUseCase,
    ExtractionFilter,
    ReanalyzeWithPromptVersionUseCase,
)
from papers.app.use_cases.pipeline import (
    EnqueueConvertUseCase,
    EnqueueDownloadUseCase,
    EnqueueEmbedUseCase,
    RunAnalysisUseCase,
)
from papers.app.use_cases.search import FilterByExtractionsUseCase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloExtractionStore,
    PiccoloJobQueue,
    PiccoloPaperProjectStore,
    PiccoloProfileStore,
    PiccoloPromptStore,
)


class Enqueue(PaperId):
    max_attempts: Annotated[int, Field(ge=1, le=100)] = 3


class Download(Enqueue):
    source_path: Path | None = None


class Analysis(Request):
    prompt_version_id: Identifier
    profile_id: Identifier
    model_name: Identifier
    force: bool = False


class AnalyzePaper(PaperId):
    prompt_id: Identifier
    prompt_version_id: Identifier | None = None
    profile_id: Identifier
    model_name: Identifier
    force: bool = False


class AnalyzeProject(Analysis):
    project_id: Identifier
    label: str | None = None
    filters: list[ProjectFilter] = []


class Reanalyze(Analysis):
    scope: Annotated[list[Identifier], Field(min_length=1, max_length=1000)]


def analysis_use_case(runtime: ApiRuntime) -> RunAnalysisUseCase:
    database(runtime)
    return RunAnalysisUseCase(
        PiccoloJobQueue(), PiccoloPromptStore(), PiccoloProfileStore(), PiccoloAnalysisRunStore()
    )


def download(runtime: ApiRuntime, request: Download) -> JsonValue:
    require_paper(runtime, request.paper_id)
    if request.source_path is None:
        job_id = PiccoloJobQueue().enqueue(
            "download", request.paper_id, None, {"max_attempts": request.max_attempts}
        )
    else:
        job_id = EnqueueDownloadUseCase(PiccoloJobQueue())(
            paper_id=request.paper_id,
            source_path=str(runtime.resolve(request.source_path)),
            max_attempts=request.max_attempts,
        )
    return {"job_id": job_id}


def convert(runtime: ApiRuntime, request: Enqueue) -> JsonValue:
    require_paper(runtime, request.paper_id)
    return {
        "job_id": EnqueueConvertUseCase(PiccoloJobQueue())(
            paper_id=request.paper_id, max_attempts=request.max_attempts
        )
    }


def embed(runtime: ApiRuntime, request: Enqueue) -> JsonValue:
    require_paper(runtime, request.paper_id)
    return {
        "job_id": EnqueueEmbedUseCase(PiccoloJobQueue())(
            paper_id=request.paper_id, max_attempts=request.max_attempts
        )
    }


def analyze(runtime: ApiRuntime, request: AnalyzePaper) -> JsonValue:
    require_paper(runtime, request.paper_id)
    return {
        "run_id": analysis_use_case(runtime)(
            paper_id=request.paper_id,
            prompt_id=request.prompt_id,
            prompt_version_id=request.prompt_version_id,
            profile_id=request.profile_id,
            model_name=request.model_name,
            force=request.force,
        )
    }


def analyze_project(runtime: ApiRuntime, request: AnalyzeProject) -> JsonValue:
    one(
        runtime,
        Query("SELECT project_id FROM projects WHERE project_id = ?", (request.project_id,)),
    )
    use_case = AnalyzeProjectUseCase(
        PiccoloPaperProjectStore(),
        PiccoloPromptStore(),
        analysis_use_case(runtime),
        FilterByExtractionsUseCase(PiccoloExtractionStore()),
    )
    return json_result(
        use_case(
            project_id=request.project_id,
            prompt_version_id=request.prompt_version_id,
            profile_id=request.profile_id,
            model_name=request.model_name,
            label=request.label,
            filters=[
                ExtractionFilter(
                    field_path=item.field_path,
                    prompt_version_id=item.prompt_version_id,
                    constraints=item.constraints.model_dump(exclude_none=True),
                    latest_only=item.latest_only,
                )
                for item in request.filters
            ],
            force=request.force,
        )
    )


def reanalyze(runtime: ApiRuntime, request: Reanalyze) -> JsonValue:
    for paper_id in request.scope:
        require_paper(runtime, paper_id)
    return json_result(
        ReanalyzeWithPromptVersionUseCase(PiccoloPromptStore(), analysis_use_case(runtime))(
            scope=request.scope,
            prompt_version_id=request.prompt_version_id,
            profile_id=request.profile_id,
            model_name=request.model_name,
            force=request.force,
        )
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.pipeline.download",
            "Queue a paper PDF download or local import.",
            Download,
            download,
            ("write",),
        ),
        Operation("papers.pipeline.convert", "Queue PDF conversion.", Enqueue, convert, ("write",)),
        Operation("papers.pipeline.embed", "Queue paper embedding.", Enqueue, embed, ("write",)),
        Operation(
            "papers.pipeline.analyze",
            "Queue analysis or reuse a successful matching run.",
            AnalyzePaper,
            analyze,
            ("write",),
        ),
        Operation(
            "papers.pipeline.analyze-project",
            "Queue project analysis with optional extraction filters.",
            AnalyzeProject,
            analyze_project,
            ("write",),
        ),
        Operation(
            "papers.pipeline.reanalyze",
            "Queue a selected paper scope with a prompt version.",
            Reanalyze,
            reanalyze,
            ("write",),
        ),
    )
