from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from pydantic import JsonValue

from gleansight.api.client import GleansightAPI
from gleansight.api.models import EmptyRequest, Success
from gleansight.api.operation import Operation, json_result
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workers.models import WorkerLimits, WorkerState
from gleansight.workers.queue import WorkerQueue
from gleansight.workers.store import WorkerStore, timestamp
from gleansight.workers.supervisor import WorkerSupervisor
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloJobQueue, PiccoloPaperStore
from tests.workers.test_supervisor import wait_phase


@pytest.mark.parametrize("fails", [False, True])
def test_api_restores_legacy_table_bindings(tmp_path: Path, fails: bool) -> None:
    configs = [ApiConfiguration(repo_root=tmp_path / name) for name in ("desktop", "api")]
    for config in configs:
        ApiRuntime(config).paper_database.bind_tables()
        PiccoloPaperStore().create_paper({"paper_id": "paper", "title": config.repo_root.name})
    ApiRuntime(configs[0]).paper_database.bind_tables()

    def read(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
        runtime.paper_database.bind_tables()
        if fails:
            raise ValueError("handler failed after initialization")
        return json_result(PiccoloPaperStore().get("paper"))

    client = GleansightAPI(configs[1], operations=(Operation("read", "read", EmptyRequest, read),))
    result = client.call("read", {})
    assert isinstance(result, Success) is not fails
    restored = PiccoloPaperStore().get("paper")
    assert restored is not None and restored["title"] == "desktop"


def test_schema_failure_restores_previous_table_bindings(tmp_path: Path) -> None:
    original = ApiRuntime(ApiConfiguration(repo_root=tmp_path / "desktop")).paper_database
    original.bind_tables()
    PiccoloPaperStore().create_paper({"paper_id": "paper", "title": "desktop"})
    other = PiccoloDatabase(tmp_path / "failed.sqlite", bind_on_init=False)
    with patch.object(PiccoloDatabase, "_create_indexes_and_fts", side_effect=ValueError("failed")):
        with pytest.raises(ValueError, match="failed"):
            other.initialize_schema()
    restored = PiccoloPaperStore().get("paper")
    assert restored is not None and restored["title"] == "desktop"


def test_concurrent_api_clients_cannot_cross_bind_tables(tmp_path: Path) -> None:
    # Given two workspaces with different values under the same paper identity.
    configs = [ApiConfiguration(repo_root=tmp_path / name) for name in ("first", "second")]
    for index, config in enumerate(configs):
        ApiRuntime(config).paper_database.bind_tables()
        PiccoloPaperStore().create_paper({"paper_id": "paper", "title": f"workspace-{index}"})
    first_bound, second_bound, release = Event(), Event(), Event()

    def read(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
        runtime.paper_database.bind_tables()
        if runtime.repo_root.name == "first":
            first_bound.set()
            assert release.wait(5)
        else:
            second_bound.set()
        return json_result(PiccoloPaperStore().get("paper"))

    clients = [
        GleansightAPI(config, operations=(Operation("read", "read", EmptyRequest, read),))
        for config in configs
    ]
    # When a second invocation overlaps a first invocation after its binding step.
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(clients[0].call, "read", {})
        assert first_bound.wait(5)
        second = executor.submit(clients[1].call, "read", {})
        serialized = not second_bound.wait(0.2)
        release.set()
        results = [first.result(), second.result()]
    # Then table bindings remain isolated for the full invocation.
    assert serialized
    for index, result in enumerate(results):
        assert isinstance(result, Success)
        assert isinstance(result.data, dict)
        assert result.data["title"] == f"workspace-{index}"


def test_atomic_claim_has_one_owner_under_competing_connections(tmp_path: Path) -> None:
    # Given one queued job and two simulated queue claimants using separate connections.
    configuration = ApiConfiguration(repo_root=tmp_path)
    runtime = ApiRuntime(configuration)
    database = runtime.paper_database
    job_id = PiccoloJobQueue().enqueue("download", "paper", None, {})
    store = WorkerStore(database.path)
    queues = []
    for worker_id in ("first", "second"):
        store.create(
            WorkerState(
                worker_id=worker_id,
                configuration=configuration,
                limits=WorkerLimits(),
                created_at=timestamp(),
                heartbeat_at=timestamp(),
                log_path="unused",
            )
        )
        queues.append(WorkerQueue(store, worker_id, None))
    # When both connections compete for the same job.
    from datetime import UTC, datetime

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda queue: queue.claim_next(datetime.now(UTC)), queues))
    # Then one claim succeeds and one attempt is recorded.
    assert sum(claim is not None for claim in claims) == 1
    assert database.fetchone("SELECT status, attempts FROM jobs WHERE job_id=?", [job_id]) == {
        "status": "running",
        "attempts": 1,
    }


def test_real_workers_consume_only_their_workspace_jobs(tmp_path: Path) -> None:
    services, jobs = [], []
    for name in ("first", "second"):
        service = WorkerSupervisor(ApiConfiguration(repo_root=tmp_path / name))
        database = ApiRuntime(service.configuration).paper_database
        source = tmp_path / name / "source.pdf"
        source.write_bytes(f"%PDF-1.4\n{name}".encode())
        PiccoloPaperStore().create_paper({"paper_id": "same-paper", "title": name})
        job_id = PiccoloJobQueue().enqueue(
            "download", "same-paper", None, {"source_path": str(source)}
        )
        services.append(service)
        jobs.append((database, job_id))
    started = [service.start(WorkerLimits(max_jobs=1, max_tokens=0)) for service in services]
    try:
        states = [
            wait_phase(service, state.worker_id, {"stopped", "failed"})
            for service, state in zip(services, started, strict=True)
        ]
        assert len({state.pid for state in states}) == 2
        for index, (database, job_id) in enumerate(jobs):
            assert states[index].jobs_processed == 1
            assert database.fetchone("SELECT status FROM jobs WHERE job_id=?", [job_id]) == {
                "status": "succeeded"
            }
            assert (
                database.fetchone("SELECT status FROM jobs WHERE job_id=?", [jobs[1 - index][1]])
                is None
            )
            (tmp_path / f"workspace-{index}-state.json").write_text(states[index].model_dump_json())
    finally:
        for service, state in zip(services, started, strict=True):
            service.control(state.worker_id, "stop")
            wait_phase(service, state.worker_id, {"stopped", "failed", "interrupted"})
