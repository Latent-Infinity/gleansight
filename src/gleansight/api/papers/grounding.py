from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import Identifier, OperationError, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from papers.domain.synthesis_grounding import GroundedSource, verify_source


class VerifySource(Request):
    source: GroundedSource
    project_id: Identifier | None = None


def verify(runtime: ApiRuntime, request: VerifySource) -> JsonValue:
    base = runtime.papers
    source = request.source
    if request.project_id is not None:
        if source.paper_id not in base.paper_project_store.list_paper_ids(request.project_id):
            raise OperationError("invalid_scope", "Source is outside the requested project.")
    paper = base.paper_store.get(source.paper_id)
    path = base.blob_store.get_markdown_path(source.paper_id)
    raw: bytes | None = None
    if paper is not None and path is not None:
        try:
            raw = path.read_bytes()
        except OSError:
            raw = None
    status = verify_source(source, raw)
    if paper is not None and str(paper.get("title") or "Untitled") != source.title:
        status = "stale"
    return json_result(
        {
            "status": status,
            "source": source.model_dump(),
            "paper": paper,
            "markdown": raw.decode("utf-8", errors="replace") if raw else None,
            "identity_only": True,
        }
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.synthesis.verify-source",
            "Check a cited passage against current Markdown.",
            VerifySource,
            verify,
        ),
    )
