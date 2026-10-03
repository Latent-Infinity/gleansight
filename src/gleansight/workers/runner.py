"""Single-process execution with limits and controls checked at job boundaries."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event

from gleansight.api.runtime import ApiRuntime
from gleansight.workers.models import WorkerState
from gleansight.workers.queue import TokenBoundUnavailable, WorkerQueue
from gleansight.workers.store import WorkerStore, timestamp
from papers.app.job_runner import JobRunner
from papers.domain.errors import BaseModuleError


def run_worker(store: WorkerStore, worker_id: str) -> None:
    state = store.get(worker_id).model_copy(update={"pid": os.getpid(), "phase": "running"})
    store.save(state)
    started = time.monotonic()
    runtime = ApiRuntime(state.configuration)
    queue = WorkerQueue(store, worker_id, state.limits.max_tokens)
    runner: JobRunner | None = None
    try:
        while True:
            state = store.get(worker_id)
            reason = _stop_reason(state, time.monotonic() - started)
            if reason is not None:
                store.save(
                    state.model_copy(
                        update={
                            "phase": "stopped",
                            "stop_reason": reason,
                            "heartbeat_at": timestamp(),
                        }
                    )
                )
                return
            phase = "paused" if state.desired_state == "pause" else "running"
            state = state.model_copy(
                update={"phase": phase, "cycles": state.cycles + 1, "heartbeat_at": timestamp()}
            )
            store.save(state)
            if state.desired_state == "pause" or not queue.eligible():
                Event().wait(state.limits.poll_interval)
                continue
            if runner is None:
                container = runtime.papers
                runner = JobRunner(
                    job_queue=queue, context=replace(container.handler_context, job_queue=queue)
                )
            # Initialization can take time; enforce controls again before claiming anything.
            latest = store.get(worker_id)
            if (
                latest.desired_state != "run"
                or time.monotonic() - started >= state.limits.max_seconds
            ):
                continue
            if runner.run_next(datetime.now(UTC)):
                state = store.get(worker_id)
                tokens = queue.recorded_tokens(state.active_job_id, state.tokens_used)
                store.save(
                    state.model_copy(
                        update={
                            "jobs_processed": state.jobs_processed + 1,
                            "active_job_id": None,
                            "active_run_id": None,
                            "tokens_used": tokens,
                            "heartbeat_at": timestamp(),
                        }
                    )
                )
    except TokenBoundUnavailable as exc:
        store.save(
            store.get(worker_id).model_copy(
                update={
                    "phase": "stopped",
                    "stop_reason": "token_bound_unavailable",
                    "error": str(exc),
                    "heartbeat_at": timestamp(),
                }
            )
        )
    except (BaseModuleError, OSError, ValueError, RuntimeError) as exc:
        store.save(
            store.get(worker_id).model_copy(
                update={"phase": "failed", "error": str(exc), "heartbeat_at": timestamp()}
            )
        )
        raise


def _stop_reason(state: WorkerState, elapsed: float) -> str | None:
    if state.desired_state == "stop":
        return "requested"
    if state.jobs_processed >= state.limits.max_jobs:
        return "job_limit"
    if state.cycles >= state.limits.max_cycles:
        return "cycle_limit"
    if elapsed >= state.limits.max_seconds:
        return "time_limit"
    return None
