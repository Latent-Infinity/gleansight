"""One owned subprocess per canonical workspace database, with durable controls."""

from __future__ import annotations

import fcntl
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workers.models import DesiredState, WorkerLimits, WorkerState
from gleansight.workers.store import WorkerStore, timestamp
from papers.domain.errors import ConflictError


def lock_path(database: Path) -> Path:
    return database.resolve().with_suffix(database.suffix + ".worker.lock")


def worker_active(database: Path) -> bool:
    path = lock_path(database)
    if not path.exists():
        return False
    with path.open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


@dataclass(frozen=True, slots=True)
class WorkerSupervisor:
    configuration: ApiConfiguration

    @property
    def database_path(self) -> Path:
        return ApiRuntime(self.configuration).settings.data.db_path.resolve()

    def start(self, limits: WorkerLimits) -> WorkerState:
        runtime = ApiRuntime(self.configuration)
        path = runtime.paper_database.path.resolve()
        store = WorkerStore(path)
        with lock_path(path).open("a+b") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                message = "A supervised worker already owns this workspace."
                raise ConflictError(message) from exc
            store.recover_orphans()
            worker_id = str(uuid4())
            directory = (
                runtime.repo_root
                / "output"
                / "workers"
                / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + worker_id)
            )
            state = WorkerState(
                worker_id=worker_id,
                configuration=self.configuration.model_copy(
                    update={"repo_root": runtime.repo_root}
                ),
                limits=limits,
                created_at=timestamp(),
                heartbeat_at=timestamp(),
                log_path=str(directory / "worker.log"),
            )
            # Starting is committed before creating artifacts or initializing any providers.
            store.create(state)
            try:
                directory.mkdir(parents=True)
                with Path(state.log_path).open("ab") as log:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "gleansight.workers",
                            "--database",
                            str(path),
                            "--worker-id",
                            worker_id,
                            "--lock-fd",
                            str(handle.fileno()),
                        ],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True,
                        pass_fds=(handle.fileno(),),
                        cwd=runtime.repo_root,
                    )
            except OSError as exc:
                store.save(state.model_copy(update={"phase": "failed", "error": str(exc)}))
                raise
            return state.model_copy(update={"pid": process.pid})

    def status(self, worker_id: str) -> WorkerState:
        state = WorkerStore(self.database_path).get(worker_id)
        if state.phase in {"starting", "running", "paused", "stopping"} and not worker_active(
            self.database_path
        ):
            return state.model_copy(
                update={
                    "phase": "interrupted",
                    "error": "Process exited before a final checkpoint.",
                }
            )
        if state.desired_state == "stop" and state.phase in {"starting", "running", "paused"}:
            return state.model_copy(update={"phase": "stopping"})
        return state

    def list(self) -> tuple[WorkerState, ...]:
        return tuple(
            self.status(state.worker_id) for state in WorkerStore(self.database_path).list()
        )

    def control(self, worker_id: str, desired: DesiredState) -> WorkerState:
        WorkerStore(self.database_path).control(worker_id, desired)
        return self.status(worker_id)
