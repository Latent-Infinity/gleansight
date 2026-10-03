from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import EmptyRequest
from gleansight.api.operation import Operation, RegisteredOperation
from gleansight.api.papers.common import database
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.admin import RebuildTitleAbstractIndexUseCase, RebuildVectorIndexUseCase
from papers.infra.piccolo.search import PiccoloPaperFTS


def rebuild_vector(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    base = runtime.papers
    return {
        "processed": RebuildVectorIndexUseCase(
            base.paper_store, base.blob_store, base.embedder, base.vector_index
        )()
    }


def rebuild_fts(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    database(runtime)
    return {"processed": RebuildTitleAbstractIndexUseCase(PiccoloPaperFTS().rebuild)()}


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.indexes.rebuild-vector",
            "Rebuild the corpus vector index.",
            EmptyRequest,
            rebuild_vector,
            ("write", "external"),
        ),
        Operation(
            "papers.indexes.rebuild-fts",
            "Rebuild the title and abstract full-text index.",
            EmptyRequest,
            rebuild_fts,
            ("write",),
        ),
    )
