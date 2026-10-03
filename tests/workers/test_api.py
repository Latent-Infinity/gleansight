from __future__ import annotations

from pathlib import Path

import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure, Success
from gleansight.api.papers.jobs import operations as job_operations
from gleansight.api.workers import operations
from gleansight.workers.models import WorkerLimits
from gleansight.workers.supervisor import WorkerSupervisor
from tests.workers.test_supervisor import supervisor as supervisor
from tests.workers.test_supervisor import wait_phase


def test_public_worker_lifecycle_and_recovery_guard(
    supervisor: WorkerSupervisor, tmp_path: Path
) -> None:
    # Given public worker and job operations sharing a real scratch workspace.
    api = GleansightAPI(supervisor.configuration, operations=(*operations(), *job_operations()))
    assert isinstance(api.call("papers.workers.list", {}), Success)
    started = api.call("papers.workers.start", {"limits": {"max_seconds": 20, "max_cycles": 500}})
    assert isinstance(started, Success) and isinstance(started.data, dict)
    worker_id = started.data["worker_id"]
    assert isinstance(worker_id, str)
    # When controls are invoked and conflicting synchronous execution is attempted.
    for operation in ("papers.workers.pause", "papers.workers.resume"):
        assert isinstance(api.call(operation, {"worker_id": worker_id}), Success)
    for operation in ("papers.jobs.recover", "papers.jobs.run-next", "papers.jobs.run-bounded"):
        conflict = api.call(operation, {})
        assert isinstance(conflict, Failure) and conflict.error.code == "conflict"
    status = api.call("papers.workers.status", {"worker_id": worker_id})
    assert isinstance(api.call("papers.workers.stop", {"worker_id": worker_id}), Success)
    stopped = wait_phase(supervisor, worker_id, {"stopped"})
    # Then durable progress is returned without internal connection configuration.
    assert isinstance(status, Success) and isinstance(status.data, dict)
    assert "configuration" not in status.data
    assert stopped.stop_reason == "requested"
    (tmp_path / "api-worker-state.json").write_text(status.model_dump_json(indent=2))


def test_public_missing_worker_and_parallelism_errors(supervisor: WorkerSupervisor) -> None:
    # Given a provider-free workspace client.
    api = GleansightAPI(supervisor.configuration, operations=operations())
    # When missing workers or unsupported parallel fanout are requested.
    missing = api.call("papers.workers.status", {"worker_id": "missing"})
    parallel = api.call("papers.workers.start", {"limits": {"concurrency": 2}})
    # Then stable boundary errors are returned.
    assert isinstance(missing, Failure) and missing.error.code == "not_found"
    assert isinstance(parallel, Failure) and parallel.error.code == "invalid_request"
    with pytest.raises(ValueError):
        WorkerLimits(max_jobs=0)
