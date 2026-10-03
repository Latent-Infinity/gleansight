"""Adapt the supported discovery path to immutable provider observations."""

from dataclasses import dataclass

from pydantic import JsonValue, TypeAdapter

from papers.app.use_cases.discovery import DiscoverCandidatesUseCase, ScholarClient
from papers.domain.screening import SavedSearch, SearchResult
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloCandidateStore


@dataclass(frozen=True, slots=True)
class CapturedResults:
    results: list[dict[str, JsonValue]]

    def search(
        self,
        query: str,
        filters: dict[str, JsonValue],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, JsonValue]]:
        return self.results


def discover(
    database: PiccoloDatabase, client: ScholarClient, search: SavedSearch
) -> tuple[SearchResult, ...]:
    filters = search.filters.model_dump(mode="json", exclude_none=True)
    raw = client.search(
        query=search.query,
        filters=filters,
        max_results=search.max_results,
        page_size=min(100, search.max_results),
        offset=0,
    )
    results = TypeAdapter(tuple[SearchResult, ...]).validate_python(raw)
    captured = CapturedResults([item.model_dump(mode="json") for item in results])
    with database.temporary_table_bindings():
        DiscoverCandidatesUseCase(captured, PiccoloCandidateStore()).discover(
            query=search.query,
            filters=filters,
            max_results=search.max_results,
        )
    return results
