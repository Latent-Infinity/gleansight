from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workers.models import DesiredState, WorkerLimits, WorkerState
from gleansight.workers.queue import TokenBoundUnavailable, WorkerQueue
from gleansight.workers.store import WorkerStore, timestamp
from gleansight.workers.supervisor import WorkerSupervisor, worker_active
from papers.infra.piccolo.stores import PiccoloAnalysisRunStore, PiccoloJobQueue
from tests.workers.test_supervisor import supervisor as supervisor
from tests.workers.test_supervisor import wait_phase


def test_relative_workspace_is_frozen_for_child_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a relative workspace path at the public boundary.
    monkeypatch.chdir(tmp_path)
    service = WorkerSupervisor(ApiConfiguration(repo_root=Path("relative")))
    # When the child changes its working directory to that workspace.
    started = service.start(WorkerLimits(max_cycles=1))
    state = wait_phase(service, started.worker_id, {"stopped"})
    # Then it retains the same canonical workspace instead of resolving a nested one.
    assert state.configuration.repo_root == tmp_path / "relative"
    assert not (tmp_path / "relative" / "relative").exists()


def test_launch_error_is_durable_and_releases_reservation(supervisor: WorkerSupervisor) -> None:
    # Given an OS launch denial at the process boundary.
    with patch(
        "gleansight.workers.supervisor.subprocess.Popen", side_effect=OSError("launch denied")
    ):
        # When launch fails, then the failed state is durable and the reservation releases.
        with pytest.raises(OSError):
            supervisor.start(WorkerLimits())
    assert supervisor.list()[0].phase == "failed"
    assert not worker_active(supervisor.database_path)


def test_real_child_initialization_failure_preserves_unclaimed_job(
    supervisor: WorkerSupervisor,
) -> None:
    # Given an invalid blob directory and a queued job.
    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    runtime.settings.data.blobs_dir.parent.mkdir(parents=True, exist_ok=True)
    runtime.settings.data.blobs_dir.write_text("file prevents directory initialization")
    job_id = PiccoloJobQueue().enqueue("download", "paper", None, {})
    # When a real worker attempts initialization.
    started = supervisor.start(WorkerLimits())
    state = wait_phase(supervisor, started.worker_id, {"failed"})
    # Then failure is visible and the job has never been claimed.
    assert state.error
    assert runtime.paper_database.fetchone(
        "SELECT status, attempts FROM jobs WHERE job_id=?", [job_id]
    ) == {"status": "queued", "attempts": 0}


@pytest.mark.parametrize(
    "usage, expected", [("missing", None), ("partial", None), ("known", 12), ("embedding", None)]
)
def test_reported_tokens_never_replace_unknown_with_zero(
    supervisor: WorkerSupervisor, usage: str, expected: int | None
) -> None:
    # Given recorded provider usage or explicit absence of that information.
    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    runs, jobs = PiccoloAnalysisRunStore(), PiccoloJobQueue()
    runs.create_run("run", "paper", "prompt", "profile", "model")
    if usage == "embedding":
        job_id = jobs.enqueue("embed", "paper", None, {})
    else:
        job_id = jobs.enqueue("analyze", "paper", "run", {})
    if usage != "missing":
        runs.mark_finished(
            "run",
            output_md="recorded-output.md",
            tokens_in=5,
            tokens_out=7 if usage == "known" else None,
        )
    # When worker progress reads the committed usage record.
    queue = WorkerQueue(WorkerStore(runtime.paper_database.path), "worker", None)
    # Then absent or unsupported usage remains unknown.
    assert queue.recorded_tokens(job_id, 0) == expected


def test_claim_rechecks_token_admission_inside_transaction(supervisor: WorkerSupervisor) -> None:
    # Given a provider job after a prior eligibility check could have raced.
    from datetime import UTC, datetime

    runtime = ApiRuntime(supervisor.configuration)
    runtime.paper_database.bind_tables()
    PiccoloJobQueue().enqueue("embed", "paper", None, {})
    store = WorkerStore(runtime.paper_database.path)
    store.create(
        WorkerState(
            worker_id="worker",
            configuration=supervisor.configuration,
            limits=WorkerLimits(max_tokens=1),
            created_at=timestamp(),
            heartbeat_at=timestamp(),
            log_path="unused",
        )
    )
    # When claiming directly, then admission is enforced in the same transaction.
    with pytest.raises(TokenBoundUnavailable):
        WorkerQueue(store, "worker", 1).claim_next(datetime.now(UTC))
    store.save(store.get("worker").model_copy(update={"phase": "stopped"}))


@pytest.mark.parametrize("desired", ["pause", "stop"])
def test_control_rechecked_inside_claim_transaction(
    supervisor: WorkerSupervisor, desired: DesiredState
) -> None:
    from datetime import UTC, datetime, timedelta

    runtime = ApiRuntime(supervisor.configuration)
    database = runtime.paper_database
    job_id = PiccoloJobQueue().enqueue("download", "paper", None, {})
    store = WorkerStore(database.path)
    store.create(
        WorkerState(
            worker_id="worker",
            configuration=supervisor.configuration,
            limits=WorkerLimits(),
            created_at=timestamp(),
            heartbeat_at=timestamp(),
            log_path="unused",
        )
    )
    queue = WorkerQueue(store, "worker", 0)
    assert queue.eligible()
    store.control("worker", desired)
    assert queue.claim_next(datetime.now(UTC)) is None
    assert database.fetchone("SELECT status FROM jobs WHERE job_id=?", [job_id]) == {
        "status": "queued"
    }
    store.control("worker", "run")
    database.execute(
        "UPDATE jobs SET run_after=? WHERE job_id=?",
        [(datetime.now(UTC) + timedelta(days=1)).isoformat(), job_id],
    )
    assert not queue.eligible()
    assert queue.claim_next(datetime.now(UTC)) is None
    assert queue.recorded_tokens("missing", 0) is None
    assert queue.recorded_tokens(job_id, None) is None
    store.save(store.get("worker").model_copy(update={"phase": "stopped"}))
    assert store.control("worker", "pause").desired_state == "run"
