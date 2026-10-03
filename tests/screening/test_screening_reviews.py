from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.domain.screening import ImportedSelection, Review, ScreeningDesk
from tests.screening.conftest import LocalScholar
from tests.screening.support import call, rerun, saved


def test_reviewer_revision_is_immutable_and_detects_stale_edits(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    candidate = rerun(client, search).observations[0].candidate_id
    request = {
        "search_id": search.search_id,
        "candidate_id": candidate,
        "decision": "maybe",
        "reviewer": "Alice",
        "rationale": "Read methods before inclusion",
        "expected_revision": 0,
    }
    first = Review.model_validate(call(client, "review", request))
    stale = client.call("papers.screening.review", request)
    assert isinstance(stale, Failure) and stale.error.code == "conflict"
    second = Review.model_validate(
        call(
            client,
            "review",
            {**request, "decision": "include", "reviewer": "Bob", "expected_revision": 1},
        )
    )
    desk = ScreeningDesk.model_validate(call(client, "get", {"search_id": search.search_id}))
    assert desk.reviews == (first, second)
    assert first.decision == "maybe" and second.decision == "include"
    assert first.reviewer == "Alice" and second.reviewer == "Bob"


def test_selected_inclusion_import_is_atomic_and_repeatable(
    client: GleansightAPI, scholar: LocalScholar, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    candidate = rerun(client, search).observations[0].candidate_id
    call(
        client,
        "review",
        {
            "search_id": search.search_id,
            "candidate_id": candidate,
            "decision": "include",
            "reviewer": "Reader",
            "rationale": "Relevant methods",
        },
    )
    rejected = client.call(
        "papers.screening.import",
        {"search_id": search.search_id, "candidate_ids": [candidate], "tag_ids": ["missing"]},
    )
    assert isinstance(rejected, Failure)
    database = ApiRuntime(configuration).paper_database
    assert database.fetchall("SELECT count(*) AS total FROM papers")[0]["total"] == 0
    first = ImportedSelection.model_validate(
        call(client, "import", {"search_id": search.search_id, "candidate_ids": [candidate]})
    )
    second = ImportedSelection.model_validate(
        call(
            client,
            "import",
            {"search_id": search.search_id, "candidate_ids": [candidate, candidate]},
        )
    )
    assert first == second
    assert database.fetchall("SELECT count(*) AS total FROM papers")[0]["total"] == 1
    assert (
        database.fetchall(
            "SELECT count(*) AS total FROM paper_projects WHERE project_id=?", ["project-1"]
        )[0]["total"]
        == 1
    )
    assert (
        database.fetchall("SELECT count(*) AS total FROM jobs WHERE type='download'")[0]["total"]
        == 1
    )


def test_excluded_candidate_cannot_be_imported(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    search = saved(client)
    candidate = rerun(client, search).observations[0].candidate_id
    call(
        client,
        "review",
        {
            "search_id": search.search_id,
            "candidate_id": candidate,
            "decision": "exclude",
            "reviewer": "Reader",
            "rationale": "Wrong domain",
        },
    )
    result = client.call(
        "papers.screening.import", {"search_id": search.search_id, "candidate_ids": [candidate]}
    )
    assert isinstance(result, Failure)


def test_review_cannot_reference_candidate_from_another_search(
    client: GleansightAPI, scholar: LocalScholar
) -> None:
    first = saved(client)
    second = saved(client)
    candidate = rerun(client, first).observations[0].candidate_id
    result = client.call(
        "papers.screening.review",
        {
            "search_id": second.search_id,
            "candidate_id": candidate,
            "decision": "include",
            "reviewer": "Reader",
            "rationale": "Relevant",
        },
    )
    assert isinstance(result, Failure)
