from collections.abc import Mapping

from pydantic import JsonValue

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Success
from papers.domain.screening import DiscoveryRun, SavedSearch


def call(client: GleansightAPI, operation: str, parameters: Mapping[str, JsonValue]) -> JsonValue:
    result = client.call("papers.screening." + operation, parameters)
    assert isinstance(result, Success), result
    return result.data


def saved(client: GleansightAPI) -> SavedSearch:
    return SavedSearch.model_validate(
        call(
            client,
            "save",
            {
                "project_id": "project-1",
                "name": "Methods",
                "query": "causal learning",
                "filters": {"year_min": 2020},
            },
        )
    )


def rerun(client: GleansightAPI, search: SavedSearch, run_id: str = "run-1") -> DiscoveryRun:
    return DiscoveryRun.model_validate(
        call(client, "rerun", {"search_id": search.search_id, "run_id": run_id})
    )
