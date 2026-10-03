from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from threading import Event

import pytest

from gleansight.api.runtime import ApiRuntime
from gleansight.workers.models import WorkerLimits
from gleansight.workers.store import WorkerStore
from gleansight.workers.supervisor import WorkerSupervisor, worker_active
from papers.infra.piccolo.stores import PiccoloJobQueue, PiccoloPaperStore
from tests.workers.test_supervisor import supervisor as supervisor
from tests.workers.test_supervisor import wait_phase


def wait_active(service: WorkerSupervisor, worker_id: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = service.status(worker_id)
        if state.active_job_id is not None:
            return
        assert state.phase not in {"failed", "interrupted"}, state.error
        Event().wait(0.05)
    pytest.fail("Worker did not claim the local blocking fixture")


def test_dead_worker_orphan_requires_retry_without_repeating_work(
    supervisor: WorkerSupervisor, tmp_path: Path
) -> None:
    # Given a real subprocess blocked reading an explicitly local FIFO source.
    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    pipe = tmp_path / "blocked.pdf"
    os.mkfifo(pipe)
    PiccoloPaperStore().create_paper({"paper_id": "paper", "title": "paper"})
    job_id = PiccoloJobQueue().enqueue("download", "paper", None, {"source_path": str(pipe)})
    started = supervisor.start(WorkerLimits(max_seconds=20))
    wait_active(supervisor, started.worker_id)
    state = supervisor.status(started.worker_id)
    assert state.pid is not None
    # When the owned process dies and a new bounded supervisor starts.
    os.kill(state.pid, signal.SIGKILL)
    deadline = time.monotonic() + 5
    while worker_active(supervisor.database_path) and time.monotonic() < deadline:
        Event().wait(0.05)
    assert not worker_active(supervisor.database_path)
    restarted = supervisor.start(WorkerLimits(max_cycles=1, max_seconds=10))
    wait_phase(supervisor, restarted.worker_id, {"stopped"})
    # Then orphaned work is marked ambiguous instead of replayed.
    row = runtime.paper_database.fetchone(
        "SELECT status, attempts, last_error FROM jobs WHERE job_id=?", [job_id]
    )
    assert row is not None and row["status"] == "failed" and row["attempts"] == 1
    assert "Explicit retry required" in row["last_error"]
    assert supervisor.status(started.worker_id).phase == "interrupted"


def test_recovery_preserves_already_committed_terminal_jobs(supervisor: WorkerSupervisor) -> None:
    # Given a succeeded job and a durable worker checkpoint from just before finalization.
    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    queue = PiccoloJobQueue()
    job_id = queue.enqueue("download", "paper", None, {})
    queue.mark_succeeded(job_id)
    started = supervisor.start(WorkerLimits(max_cycles=1))
    stopped = wait_phase(supervisor, started.worker_id, {"stopped"})
    store = WorkerStore(supervisor.database_path)
    store.save(stopped.model_copy(update={"phase": "running", "active_job_id": job_id}))
    # When a fresh process recovers that durable checkpoint.
    restarted = supervisor.start(WorkerLimits(max_cycles=1))
    wait_phase(supervisor, restarted.worker_id, {"stopped"})
    # Then the successful commit is retained without another attempt.
    assert runtime.paper_database.fetchone(
        "SELECT status, attempts FROM jobs WHERE job_id=?", [job_id]
    ) == {"status": "succeeded", "attempts": 0}


@pytest.mark.parametrize(
    "limits, expected",
    [
        (WorkerLimits(max_cycles=1, max_seconds=20), "cycle_limit"),
        (WorkerLimits(max_cycles=1000, max_seconds=0.1), "time_limit"),
    ],
)
def test_empty_worker_stops_at_declared_boundary(
    supervisor: WorkerSupervisor, limits: WorkerLimits, expected: str
) -> None:
    # Given an empty workspace and one explicit bound.
    # When a real worker executes until that boundary.
    started = supervisor.start(limits)
    state = wait_phase(supervisor, started.worker_id, {"stopped"})
    # Then the persisted stop reason identifies the actual boundary.
    assert state.stop_reason == expected
    assert state.jobs_processed == 0


def test_stop_waits_for_active_local_call_checkpoint(
    supervisor: WorkerSupervisor, tmp_path: Path
) -> None:
    # Given a real local read blocked until the test releases its FIFO.
    from papers.infra.blobs_fs.store import FileSystemBlobStore

    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    content = b"%PDF-1.4\ncheckpoint fixture"
    source = tmp_path / "source.pdf"
    source.write_bytes(content)
    FileSystemBlobStore(runtime.settings.data.blobs_dir).put_pdf(source)
    pipe = tmp_path / "blocked.pdf"
    os.mkfifo(pipe)
    PiccoloPaperStore().create_paper({"paper_id": "paper", "title": "paper"})
    job_id = PiccoloJobQueue().enqueue("download", "paper", None, {"source_path": str(pipe)})
    started = supervisor.start(WorkerLimits(max_seconds=20))
    wait_active(supervisor, started.worker_id)
    # When stop is requested during that call, it remains active until its checkpoint.
    pending = supervisor.control(started.worker_id, "stop")
    assert pending.phase == "stopping" and pending.active_job_id == job_id
    assert runtime.paper_database.fetchone("SELECT status FROM jobs WHERE job_id=?", [job_id]) == {
        "status": "running"
    }
    pipe.write_bytes(content)
    completed = wait_phase(supervisor, started.worker_id, {"stopped"})
    # Then the completed work is retained and no additional job is claimed.
    assert completed.jobs_processed == 1 and completed.stop_reason == "requested"
    assert runtime.paper_database.fetchone("SELECT status FROM jobs WHERE job_id=?", [job_id]) == {
        "status": "succeeded"
    }
