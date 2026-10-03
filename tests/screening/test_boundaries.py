import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workspaces.backup import backup_workspace
from gleansight.workspaces.layout import workspace_layout
from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.app.use_cases.saved_discovery.claims import discovery_claim
from papers.domain.errors import ConfigurationError, ConflictError
from papers.domain.screening import SaveSearch, ScreeningDesk, SearchResult
from tests.screening.conftest import LocalScholar
from tests.screening.support import call, rerun, saved


def test_inflight_discovery_refuses_backup(configuration: ApiConfiguration) -> None:
    runtime = ApiRuntime(configuration)
    service = SavedDiscoveryService(runtime.paper_database)
    search = service.save(SaveSearch(project_id="project-1", name="Claim", query="query"))
    with discovery_claim(service.store, search.search_id, "active-discovery", managed=False):
        with pytest.raises(ConflictError):
            backup_workspace(workspace_layout(runtime), configuration.repo_root / "output/backups")
    assert (
        runtime.paper_database.fetchall("SELECT status FROM jobs WHERE job_id='active-discovery'")[
            0
        ]["status"]
        == "succeeded"
    )


def test_provider_is_required_only_for_new_reruns(
    client: GleansightAPI, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    with pytest.raises(ConfigurationError):
        SavedDiscoveryService(ApiRuntime(configuration).paper_database).rerun(search.search_id)


def test_existing_claim_is_refused_without_provider_calls(
    client: GleansightAPI, scholar: LocalScholar, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    service = SavedDiscoveryService(ApiRuntime(configuration).paper_database, scholar)
    with discovery_claim(service.store, search.search_id, "active-run", managed=False):
        with pytest.raises(ConflictError):
            service.rerun(search.search_id, "active-run")
    assert scholar.calls == 0


def test_failed_claim_records_terminal_failure(
    client: GleansightAPI, scholar: LocalScholar, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    with pytest.raises(ConflictError):
        with discovery_claim(
            SavedDiscoveryService(ApiRuntime(configuration).paper_database).store,
            search.search_id,
            "failed-run",
            managed=False,
        ):
            raise ConflictError("Provider refused request")
    assert (
        ApiRuntime(configuration).paper_database.fetchall(
            "SELECT status FROM jobs WHERE job_id='failed-run'"
        )[0]["status"]
        == "failed"
    )


def test_run_identifier_cannot_cross_saved_queries(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    first = saved(client)
    second = saved(client)
    rerun(client, first)
    result = client.call(
        "papers.screening.rerun", {"search_id": second.search_id, "run_id": "run-1"}
    )
    assert isinstance(result, Failure)
    assert scholar.calls == 1


def test_source_alias_cannot_switch_to_another_known_doi(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    scholar.results += (
        SearchResult(
            source_paper_id="other", title="Other paper", external_ids={"DOI": "10.42/other"}
        ),
    )
    rerun(client, search)
    scholar.results = (
        scholar.results[0].model_copy(update={"external_ids": {"DOI": "10.42/other"}}),
    )
    result = client.call("papers.screening.rerun", {"search_id": search.search_id})
    assert isinstance(result, Failure)
    assert (
        len(ScreeningDesk.model_validate(call(client, "get", {"search_id": search.search_id})).runs)
        == 1
    )
