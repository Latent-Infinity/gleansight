import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure
from gleansight.api.runtime import ApiConfiguration
from papers.domain.screening import ScreeningDesk, SearchResult
from tests.screening.conftest import LocalScholar
from tests.screening.support import call, rerun, saved


def test_restart_rerun_distinguishes_seen_and_metadata_change(
    client: GleansightAPI, scholar: LocalScholar, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    first = rerun(client, search)
    second = rerun(client, search, "run-2")
    scholar.results = (
        scholar.results[0].model_copy(update={"title": "Updated causal discovery"}),
        SearchResult(source_paper_id="s2-2", title="New paper"),
    )
    third = rerun(client, search, "run-3")
    restarted = GleansightAPI(configuration)
    desk = ScreeningDesk.model_validate(call(restarted, "get", {"search_id": search.search_id}))
    assert [item.delta for item in first.observations] == ["new"]
    assert [item.delta for item in second.observations] == ["seen"]
    assert [item.delta for item in third.observations] == ["metadata_changed", "new"]
    assert desk.runs == (first, second, third)
    assert desk.runs[0].observations[0].metadata.title == "Causal discovery"


def test_duplicate_doi_retains_provider_alias_and_reuses_canonical_candidate(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    first = rerun(client, search)
    scholar.results = (
        scholar.results[0].model_copy(
            update={"source_paper_id": "alternate-s2", "external_ids": {"DOI": "doi:10.42/abc"}}
        ),
    )
    second = rerun(client, search, "run-2")
    assert second.observations[0].candidate_id == first.observations[0].candidate_id
    assert second.observations[0].source_paper_id == "alternate-s2"
    assert first.observations[0].source_paper_id == "s2-1"
    assert second.observations[0].delta == "seen"


def test_repeated_run_identity_does_not_call_provider_again(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    first = rerun(client, search)
    assert rerun(client, search) == first
    assert scholar.calls == 1


def test_changed_doi_for_existing_source_is_rejected_without_rewriting_history(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    first = rerun(client, search)
    scholar.results = (
        scholar.results[0].model_copy(update={"external_ids": {"DOI": "10.42/different"}}),
    )
    result = client.call(
        "papers.screening.rerun", {"search_id": search.search_id, "run_id": "run-2"}
    )
    assert isinstance(result, Failure)
    desk = ScreeningDesk.model_validate(call(client, "get", {"search_id": search.search_id}))
    assert desk.runs == (first,)


@pytest.mark.parametrize(
    "parameters",
    [
        {"project_id": "missing", "name": "Test", "query": "query"},
        {
            "project_id": "project-1",
            "name": "Test",
            "query": "query",
            "filters": {"year_min": 2025, "year_max": 2020},
        },
        {"project_id": "project-1", "name": "Test", "query": "query", "api_key": "secret"},
    ],
)
def test_invalid_saved_search_is_rejected(
    client: GleansightAPI, parameters: dict[str, str]
) -> None:
    result = client.call("papers.screening.save", parameters)
    assert isinstance(result, Failure)
    assert call(client, "list", {}) == []


def test_new_external_metadata_is_reported_as_change(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    rerun(client, search)
    scholar.results = (
        scholar.results[0].model_copy(
            update={
                "external_ids": {
                    "DOI": "10.42/abc",
                    "OpenAccessPdf": "https://example.org/paper.pdf",
                }
            }
        ),
    )
    second = rerun(client, search, "run-2")
    assert second.observations[0].delta == "metadata_changed"
