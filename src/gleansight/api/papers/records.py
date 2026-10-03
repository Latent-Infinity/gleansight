from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import Identifier, OperationError
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.common import (
    Page,
    PaperId,
    Query,
    RunId,
    database,
    one,
    page,
    require_paper,
)
from gleansight.api.runtime import ApiRuntime
from papers.domain.models import PipelineStage
from papers.infra.piccolo.stores import PiccoloPaperStore


class PaperPage(Page):
    stage: PipelineStage | None = None


class ResetStage(PaperId):
    stage: PipelineStage


class Runs(Page):
    paper_id: Identifier | None = None


class Extractions(Page):
    paper_id: Identifier
    prompt_version_id: Identifier | None = None


def list_papers(runtime: ApiRuntime, request: PaperPage) -> JsonValue:
    query = Query("SELECT * FROM papers ORDER BY paper_id")
    if request.stage is not None:
        query = Query(
            "SELECT * FROM papers WHERE pipeline_stage = ? ORDER BY paper_id",
            (request.stage.value,),
        )
    return page(runtime, query, request)


def get(runtime: ApiRuntime, request: PaperId) -> JsonValue:
    require_paper(runtime, request.paper_id)
    return json_result(PiccoloPaperStore().get(request.paper_id))


def markdown(runtime: ApiRuntime, request: PaperId) -> JsonValue:
    require_paper(runtime, request.paper_id)
    root = (runtime.settings.data.blobs_dir / "md").resolve()
    path = (root / f"{request.paper_id}.md").resolve()
    if not path.is_relative_to(root):
        raise OperationError(
            "invalid_path", "Paper markdown must remain inside the blob directory."
        )
    if not path.is_file():
        raise OperationError("not_found", "Paper markdown is not available.")
    return {"paper_id": request.paper_id, "markdown": path.read_text(encoding="utf-8")}


def delete(runtime: ApiRuntime, request: PaperId) -> JsonValue:
    require_paper(runtime, request.paper_id)
    PiccoloPaperStore().delete_paper(request.paper_id)
    return {"deleted": True}


def reset(runtime: ApiRuntime, request: ResetStage) -> JsonValue:
    require_paper(runtime, request.paper_id)
    PiccoloPaperStore().reset_pipeline_stage(request.paper_id, request.stage.value)
    return {"paper_id": request.paper_id, "stage": request.stage.value}


def runs(runtime: ApiRuntime, request: Runs) -> JsonValue:
    query = Query("SELECT * FROM analysis_runs ORDER BY created_at, run_id")
    if request.paper_id is not None:
        query = Query(
            "SELECT * FROM analysis_runs WHERE paper_id = ? ORDER BY created_at, run_id",
            (request.paper_id,),
        )
    return page(runtime, query, request)


def extractions(runtime: ApiRuntime, request: Extractions) -> JsonValue:
    database(runtime)
    query = Query(
        "SELECT * FROM analysis_extractions WHERE paper_id = ? ORDER BY extraction_id",
        (request.paper_id,),
    )
    if request.prompt_version_id is not None:
        query = Query(
            "SELECT * FROM analysis_extractions WHERE paper_id = ? "
            "AND prompt_version_id = ? ORDER BY extraction_id",
            (request.paper_id, request.prompt_version_id),
        )
    return page(runtime, query, request)


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.papers.list", "List corpus papers with pagination.", PaperPage, list_papers
        ),
        Operation("papers.papers.get", "Get a corpus paper.", PaperId, get),
        Operation(
            "papers.papers.get-markdown", "Read converted paper markdown.", PaperId, markdown
        ),
        Operation(
            "papers.papers.delete",
            "Delete a paper and its database dependents.",
            PaperId,
            delete,
            ("write",),
        ),
        Operation(
            "papers.papers.reset-stage",
            "Reset a paper's pipeline stage and health.",
            ResetStage,
            reset,
            ("write",),
        ),
        Operation("papers.runs.list", "List analysis runs with pagination.", Runs, runs),
        Operation(
            "papers.runs.get",
            "Get an analysis run.",
            RunId,
            lambda r, q: one(r, Query("SELECT * FROM analysis_runs WHERE run_id = ?", (q.run_id,))),
        ),
        Operation(
            "papers.runs.extractions",
            "List paper extractions with pagination.",
            Extractions,
            extractions,
        ),
    )
