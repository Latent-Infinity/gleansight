from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event

import pytest

from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workers.models import WorkerLimits, WorkerState
from gleansight.workers.supervisor import WorkerSupervisor
from papers.domain.errors import ConflictError
from papers.infra.piccolo.stores import PiccoloJobQueue, PiccoloPaperStore


@pytest.fixture
def supervisor(tmp_path: Path) -> Iterator[WorkerSupervisor]:
    service = WorkerSupervisor(ApiConfiguration(repo_root=tmp_path))
    yield service
    for state in service.list():
        if state.phase in {"starting", "running", "paused", "stopping"}:
            service.control(state.worker_id, "stop")
            wait_phase(service, state.worker_id, {"stopped", "failed", "interrupted"})


def wait_phase(service: WorkerSupervisor, worker_id: str, phases: set[str]) -> WorkerState:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = service.status(worker_id)
        if state.phase in phases:
            return state
        Event().wait(0.05)
    pytest.fail(f"Worker did not enter {phases}; last state: {state}")


def test_real_worker_start_pause_resume_stop(supervisor: WorkerSupervisor) -> None:
    # Given an empty workspace and a bounded real subprocess.
    started = supervisor.start(WorkerLimits(max_cycles=500, max_jobs=5, max_seconds=20))
    # When intake pauses, resumes and stops through durable controls.
    supervisor.control(started.worker_id, "pause")
    paused = wait_phase(supervisor, started.worker_id, {"paused"})
    supervisor.control(started.worker_id, "run")
    running = wait_phase(supervisor, started.worker_id, {"running"})
    supervisor.control(started.worker_id, "stop")
    stopped = wait_phase(supervisor, started.worker_id, {"stopped"})
    # Then process identity and state survive new client objects without fabricating work.
    assert paused.pid and running.pid == paused.pid
    assert stopped.jobs_processed == 0
    assert WorkerSupervisor(supervisor.configuration).status(started.worker_id).phase == "stopped"


def test_workspace_allows_only_one_supervisor(supervisor: WorkerSupervisor) -> None:
    # Given one live worker holding the workspace process lock.
    supervisor.start(WorkerLimits(max_cycles=500, max_jobs=5, max_seconds=20))
    # When another client starts work in that workspace, then it is rejected.
    with pytest.raises(ConflictError):
        WorkerSupervisor(supervisor.configuration).start(WorkerLimits())


def test_real_download_commit_is_bounded_and_not_repeated(
    supervisor: WorkerSupervisor, tmp_path: Path
) -> None:
    # Given a local file and two queued jobs; no live provider is involved.
    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    source = tmp_path / "local.pdf"
    source.write_bytes(b"%PDF-1.4\nlocal fixture")
    store, queue = PiccoloPaperStore(), PiccoloJobQueue()
    for paper_id in ("first", "second"):
        store.create_paper({"paper_id": paper_id, "title": paper_id})
        queue.enqueue("download", paper_id, None, {"source_path": str(source)})
    # When one job is allowed under an explicit zero-token limit.
    started = supervisor.start(
        WorkerLimits(max_cycles=50, max_jobs=1, max_seconds=20, max_tokens=0)
    )
    finished = wait_phase(supervisor, started.worker_id, {"stopped", "failed"})
    # Then exactly one local commit occurs and provider-dependent follow-on work remains queued.
    assert finished.phase == "stopped", finished.error
    assert finished.jobs_processed == 1
    rows = runtime.paper_database.fetchall(
        "SELECT * FROM jobs WHERE type = 'download' ORDER BY created_at"
    )
    assert [row["status"] for row in rows].count("succeeded") == 1
    assert finished.tokens_used == 0
    assert finished.stop_reason == "job_limit"
    (tmp_path / "worker-result.json").write_text(finished.model_dump_json(indent=2))


def test_token_bound_refuses_unknown_provider_intake(supervisor: WorkerSupervisor) -> None:
    # Given an embedding job whose provider token upper bound is unavailable.
    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    job_id = PiccoloJobQueue().enqueue("embed", "paper", None, {})
    # When the worker is started with an explicit token limit.
    started = supervisor.start(WorkerLimits(max_tokens=10, max_seconds=20))
    finished = wait_phase(supervisor, started.worker_id, {"stopped", "failed"})
    # Then no provider job is claimed and the unavailable bound is explicit.
    assert finished.stop_reason == "token_bound_unavailable"
    assert finished.jobs_processed == 0
    assert runtime.paper_database.fetchone(
        "SELECT status FROM jobs WHERE job_id = ?", [job_id]
    ) == {"status": "queued"}
