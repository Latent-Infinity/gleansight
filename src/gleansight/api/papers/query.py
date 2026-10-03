from __future__ import annotations

from typing import Annotated

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.common import database
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.search import (
    AggregateExtractionsUseCase,
    FilterByExtractionsUseCase,
    SearchPapersUseCase,
)
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import PiccoloExtractionStore


class Search(Request):
    query: Identifier
    limit: Annotated[int, Field(ge=1, le=1000)] = 50


class Constraints(Request):
    value_text: str | None = None
    value_numeric: float | None = None
    value_boolean: bool | None = None


class ScopedConstraints(Constraints):
    entity_type: str | None = None
    entity_ref: str | None = None
    paper_id: Identifier | None = None
    run_id: Identifier | None = None


class Aggregate(Request):
    field_path: Identifier
    prompt_version_id: Identifier
    latest_only: bool = True


class ProjectFilter(Aggregate):
    constraints: Constraints = Field(default_factory=Constraints)


class Filter(Aggregate):
    constraints: ScopedConstraints = Field(default_factory=ScopedConstraints)


class Average(Aggregate):
    group_by: Identifier | None = None


def search(runtime: ApiRuntime, request: Search) -> JsonValue:
    container = runtime.papers
    return json_result(
        SearchPapersUseCase(PiccoloPaperFTS(), container.vector_index, container.embedder).search(
            request.query, request.limit
        )
    )


def filter_extractions(runtime: ApiRuntime, request: Filter) -> JsonValue:
    database(runtime)
    return json_result(
        FilterByExtractionsUseCase(PiccoloExtractionStore()).filter(
            field_path=request.field_path,
            prompt_version_id=request.prompt_version_id,
            constraints=request.constraints.model_dump(exclude_none=True),
            latest_only=request.latest_only,
        )
    )


def count(runtime: ApiRuntime, request: Aggregate) -> JsonValue:
    database(runtime)
    return json_result(
        AggregateExtractionsUseCase(PiccoloExtractionStore()).count_by_value(
            request.field_path, request.prompt_version_id, request.latest_only
        )
    )


def average(runtime: ApiRuntime, request: Average) -> JsonValue:
    database(runtime)
    return json_result(
        AggregateExtractionsUseCase(PiccoloExtractionStore()).average_numeric(
            request.field_path, request.prompt_version_id, request.group_by, request.latest_only
        )
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.query.search",
            "Search the corpus with full-text and vector ranking.",
            Search,
            search,
            ("read", "external"),
        ),
        Operation(
            "papers.query.filter",
            "Filter paper IDs by typed extraction constraints.",
            Filter,
            filter_extractions,
        ),
        Operation("papers.query.count", "Count extraction values.", Aggregate, count),
        Operation(
            "papers.query.average",
            "Average numeric extractions, optionally grouped.",
            Average,
            average,
        ),
    )
