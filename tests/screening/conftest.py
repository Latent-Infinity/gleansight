from pathlib import Path

import pytest
from pydantic import JsonValue

from gleansight.api.client import GleansightAPI
from gleansight.api.papers import screening
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.domain.screening import SearchResult
from papers.infra.piccolo.stores import PiccoloProjectStore


class LocalScholar:
    """Deterministic provider boundary; successive responses are controlled by the scenario."""

    def __init__(self) -> None:
        self.results: tuple[SearchResult, ...] = (
            SearchResult(
                source_paper_id="s2-1",
                title="Causal discovery",
                year=2025,
                authors=("Researcher 研究",),
                external_ids={"DOI": "https://doi.org/10.42/ABC"},
            ),
        )
        self.calls = 0

    def search(
        self,
        query: str,
        filters: dict[str, JsonValue],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, JsonValue]]:
        self.calls += 1
        return [item.model_dump(mode="json") for item in self.results[:max_results]]


@pytest.fixture
def scholar(monkeypatch: pytest.MonkeyPatch) -> LocalScholar:
    client = LocalScholar()

    def build(*, api_key: str | None, rate_limit_per_second: float) -> LocalScholar:
        return client

    monkeypatch.setattr(screening, "build_s2_client", build)
    return client


@pytest.fixture
def configuration(tmp_path: Path) -> ApiConfiguration:
    configuration = ApiConfiguration(repo_root=tmp_path)
    runtime = ApiRuntime(configuration)
    runtime.paper_database.bind_tables()
    PiccoloProjectStore().create_project("project-1", "Literature review")
    return configuration


@pytest.fixture
def client(configuration: ApiConfiguration) -> GleansightAPI:
    return GleansightAPI(configuration, operations=screening.operations())
