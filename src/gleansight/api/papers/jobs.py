from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import JsonValue

from gleansight.api.models import EmptyRequest, OperationError
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.common import Query, database, one, page
from gleansight.api.papers.enqueue import enqueue, retry
from gleansight.api.papers.job_requests import (
    EnqueueJob,
    JobId,
    JobIds,
    JobPage,
    Recover,
    RunBounded,
)
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.admin import RecoverStuckJobsUseCase
from papers.infra.piccolo.stores import PiccoloJobQueue


def list_jobs(runtime: ApiRuntime, request: JobPage) -> JsonValue:
    clauses: list[str] = []
    parameters: list[JsonValue] = []
    if request.status is not None:
        clauses.append("status = ?")
        parameters.append(request.status.value)
    if request.paper_id is not None:
        clauses.append("paper_id = ?")
        parameters.append(request.paper_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return page(
        runtime,
        Query("SELECT * FROM jobs" + where + " ORDER BY created_at, job_id", tuple(parameters)),
        request,
    )


def status(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    return json_result(
        database(runtime).fetchall(
            "SELECT status, count(*) AS count FROM jobs GROUP BY status ORDER BY status"
        )
    )


def cancel(runtime: ApiRuntime, request: JobId) -> JsonValue:
    one(runtime, Query("SELECT job_id FROM jobs WHERE job_id = ?", (request.job_id,)))
    return {"canceled": PiccoloJobQueue().bulk_cancel_jobs([request.job_id])}


def delete(runtime: ApiRuntime, request: JobId) -> JsonValue:
    one(runtime, Query("SELECT job_id FROM jobs WHERE job_id = ?", (request.job_id,)))
    return bulk_delete(runtime, JobIds(job_ids=[request.job_id]))


def bulk_delete(runtime: ApiRuntime, request: JobIds) -> JsonValue:
    db = database(runtime)
    placeholders = ",".join("?" for _ in request.job_ids)
    running = db.fetchone(
        f"SELECT job_id FROM jobs WHERE status = 'running' AND job_id IN ({placeholders}) LIMIT 1",
        list(request.job_ids),
    )
    if running is not None:
        raise OperationError("conflict", "Cancel running jobs before deleting them.")
    return {"deleted": PiccoloJobQueue().bulk_delete_jobs(request.job_ids)}


def bulk_cancel(runtime: ApiRuntime, request: JobIds) -> JsonValue:
    database(runtime)
    return {"canceled": PiccoloJobQueue().bulk_cancel_jobs(request.job_ids)}


def run_next(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    return {"processed": runtime.papers.job_runner.run_next(datetime.now(UTC))}


def run_bounded(runtime: ApiRuntime, request: RunBounded) -> JsonValue:
    runner = runtime.papers.job_runner
    processed = 0
    for _ in range(request.max_jobs):
        if not runner.run_next(datetime.now(UTC)):
            break
        processed += 1
    return {"processed": processed}


def recover(runtime: ApiRuntime, request: Recover) -> JsonValue:
    database(runtime)
    return json_result(
        RecoverStuckJobsUseCase(PiccoloJobQueue(), timedelta(seconds=request.stuck_after_seconds))()
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation("papers.jobs.list", "List jobs with pagination.", JobPage, list_jobs),
        Operation(
            "papers.jobs.get",
            "Get a job, including errors and attempts.",
            JobId,
            lambda r, q: one(r, Query("SELECT * FROM jobs WHERE job_id = ?", (q.job_id,))),
        ),
        Operation("papers.jobs.status", "Count all jobs by status.", EmptyRequest, status),
        Operation(
            "papers.jobs.enqueue", "Enqueue a typed supported job.", EnqueueJob, enqueue, ("write",)
        ),
        Operation(
            "papers.jobs.cancel", "Cancel a queued or running job.", JobId, cancel, ("write",)
        ),
        Operation(
            "papers.jobs.delete", "Delete a job that is not running.", JobId, delete, ("write",)
        ),
        Operation(
            "papers.jobs.bulk-cancel",
            "Cancel queued or running jobs in a bounded selection.",
            JobIds,
            bulk_cancel,
            ("write",),
        ),
        Operation(
            "papers.jobs.bulk-delete",
            "Delete a bounded selection of jobs that are not running.",
            JobIds,
            bulk_delete,
            ("write",),
        ),
        Operation(
            "papers.jobs.retry",
            "Retry a terminal job; analysis creates a fresh run.",
            JobId,
            retry,
            ("write",),
        ),
        Operation(
            "papers.jobs.run-next",
            "Execute the next eligible job.",
            EmptyRequest,
            run_next,
            ("write", "external"),
        ),
        Operation(
            "papers.jobs.run-bounded",
            "Execute up to a bounded number of eligible jobs.",
            RunBounded,
            run_bounded,
            ("write", "external"),
        ),
        Operation(
            "papers.jobs.recover",
            "Requeue jobs whose running lease is stale.",
            Recover,
            recover,
            ("write",),
        ),
    )
