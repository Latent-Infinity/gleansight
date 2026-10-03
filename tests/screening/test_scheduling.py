from datetime import UTC, datetime, timedelta

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.domain.screening import ScheduledSearch
from tests.screening.conftest import LocalScholar
from tests.screening.support import call, saved


def test_schedule_survives_restart_and_is_idempotent(
    client: GleansightAPI, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    first_run = datetime.now(UTC) + timedelta(days=1)
    request = {
        "search_id": search.search_id,
        "first_run": first_run.isoformat(),
        "interval_minutes": 60,
        "runs": 2,
        "request_id": "weekly-search",
    }
    first = ScheduledSearch.model_validate(call(client, "schedule", request))
    again = ScheduledSearch.model_validate(call(client, "schedule", request))
    assert first == again and len(first.job_ids) == 2
    database = ApiRuntime(configuration).paper_database
    rows = database.fetchall("SELECT status, run_after, payload_json FROM jobs ORDER BY run_after")
    assert len(rows) == 2 and all(row["status"] == "queued" for row in rows)
    assert str(rows[0]["run_after"]).startswith(first_run.date().isoformat())
    conflict = client.call("papers.screening.schedule", {**request, "runs": 3})
    assert isinstance(conflict, Failure)


def test_managed_rerun_uses_claimed_queue_identity_once(
    client: GleansightAPI, scholar: LocalScholar, configuration: ApiConfiguration
) -> None:
    search = saved(client)
    scheduled = ScheduledSearch.model_validate(
        call(
            client,
            "schedule",
            {
                "search_id": search.search_id,
                "first_run": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "runs": 1,
                "request_id": "one-run",
            },
        )
    )
    database = ApiRuntime(configuration).paper_database
    database.execute("UPDATE jobs SET status='running' WHERE job_id=?", [scheduled.job_ids[0]])
    service = SavedDiscoveryService(database, scholar)
    first = service.rerun(search.search_id, scheduled.job_ids[0], managed=True)
    assert service.rerun(search.search_id, scheduled.job_ids[0], managed=True) == first
    assert scholar.calls == 1


def test_invalid_schedule_is_rejected(client: GleansightAPI) -> None:
    search = saved(client)
    result = client.call(
        "papers.screening.schedule",
        {
            "search_id": search.search_id,
            "first_run": "2000-01-01T00:00:00+00:00",
            "runs": 1,
            "request_id": "past",
        },
    )
    assert isinstance(result, Failure)


def test_future_rerun_obeys_managed_queue_and_handler_boundaries(
    client: GleansightAPI, scholar: LocalScholar, configuration: ApiConfiguration
) -> None:
    from dataclasses import replace

    from gleansight.workers.models import WorkerLimits, WorkerState
    from gleansight.workers.queue import WorkerQueue
    from gleansight.workers.store import WorkerStore, timestamp
    from papers.app.job_runner.handlers import handle_discover

    search = saved(client)
    due = datetime.now(UTC) + timedelta(days=1)
    scheduled = ScheduledSearch.model_validate(
        call(
            client,
            "schedule",
            {
                "search_id": search.search_id,
                "first_run": due.isoformat(),
                "runs": 1,
                "request_id": "bounded-worker",
            },
        )
    )
    runtime = ApiRuntime(configuration)
    base = runtime.papers
    store = WorkerStore(base.db.path)
    store.create(
        WorkerState(
            worker_id="screening-worker",
            configuration=configuration,
            limits=WorkerLimits(max_jobs=1, max_tokens=0),
            created_at=timestamp(),
            heartbeat_at=timestamp(),
            log_path="worker.log",
        )
    )
    queue = WorkerQueue(store, "screening-worker", max_tokens=0)
    assert queue.claim_next(datetime.now(UTC)) is None
    job = queue.claim_next(due + timedelta(seconds=1))
    assert job is not None and job.job_id == scheduled.job_ids[0]
    context = replace(base.handler_context, scholar_client=scholar, job_queue=queue)
    assert handle_discover(job, replace(context, database=None)).status == "failed"
    assert handle_discover(job, context).status == "succeeded"
    queue.mark_succeeded(job.job_id)
    assert SavedDiscoveryService(base.db).get(search.search_id).runs[0].run_id == job.job_id
    assert scholar.calls == 1
