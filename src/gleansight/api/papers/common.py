from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, OperationError, Request
from gleansight.api.operation import json_result
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.database import PiccoloDatabase


class Page(Request):
    limit: Annotated[int, Field(ge=1, le=1000)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


class PaperId(Request):
    paper_id: Identifier


class ProjectId(Request):
    project_id: Identifier


class TagId(Request):
    tag_id: Identifier


class PromptId(Request):
    prompt_id: Identifier


class RunId(Request):
    run_id: Identifier


@dataclass(frozen=True, slots=True)
class Query:
    sql: str
    parameters: tuple[JsonValue, ...] = ()


def database(runtime: ApiRuntime) -> PiccoloDatabase:
    db = runtime.paper_database
    db.bind_tables()
    return db


def page(runtime: ApiRuntime, query: Query, request: Page) -> JsonValue:
    rows = database(runtime).fetchall(
        query.sql + " LIMIT ? OFFSET ?",
        [*query.parameters, request.limit + 1, request.offset],
    )
    return json_result(
        {
            "items": rows[: request.limit],
            "next_offset": request.offset + request.limit if len(rows) > request.limit else None,
        }
    )


def one(runtime: ApiRuntime, query: Query) -> JsonValue:
    row = database(runtime).fetchone(query.sql, list(query.parameters))
    if row is None:
        raise OperationError("not_found", "The requested record does not exist.")
    return json_result(row)


def require_paper(runtime: ApiRuntime, paper_id: str) -> None:
    one(runtime, Query("SELECT paper_id FROM papers WHERE paper_id = ?", (paper_id,)))
