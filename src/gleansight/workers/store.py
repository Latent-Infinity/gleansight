"""Explicit-workspace SQLite persistence for worker progress and intake controls."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gleansight.workers.models import DesiredState, WorkerState
from papers.domain.errors import NotFoundError


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class WorkerStore:
    path: Path

    def create(self, state: WorkerState) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS supervised_workers "
                "(worker_id TEXT PRIMARY KEY, desired_state TEXT NOT NULL, "
                "phase TEXT NOT NULL, document_json TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO supervised_workers VALUES (?, ?, ?, ?)",
                (state.worker_id, state.desired_state, state.phase, state.model_dump_json()),
            )

    def get(self, worker_id: str) -> WorkerState:
        for state in self.list():
            if state.worker_id == worker_id:
                return state
        message = f"Worker not found: {worker_id}"
        raise NotFoundError(message)

    def list(self) -> tuple[WorkerState, ...]:
        if not self.path.exists():
            return ()
        with closing(sqlite3.connect(self.path)) as connection:
            if (
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='supervised_workers'"
                ).fetchone()
                is None
            ):
                return ()
            rows = connection.execute(
                "SELECT desired_state, phase, document_json "
                "FROM supervised_workers ORDER BY rowid DESC"
            ).fetchall()
        return tuple(
            WorkerState.model_validate(
                {
                    **WorkerState.model_validate_json(row[2]).model_dump(),
                    "desired_state": row[0],
                    "phase": row[1],
                }
            )
            for row in rows
        )

    def save(self, state: WorkerState) -> None:
        """Progress updates preserve concurrent intake-control requests."""
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE supervised_workers SET phase = ?, document_json = ? WHERE worker_id = ?",
                (state.phase, state.model_dump_json(), state.worker_id),
            )

    def control(self, worker_id: str, desired: DesiredState) -> WorkerState:
        state = self.get(worker_id)
        if state.phase not in {"stopped", "failed", "interrupted"}:
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute(
                    "UPDATE supervised_workers SET desired_state = ? WHERE worker_id = ?",
                    (desired, worker_id),
                )
        return self.get(worker_id)

    def recover_orphans(self) -> None:
        """Called only while owning the process lock; never repeat ambiguous provider work."""
        for state in self.list():
            if state.phase in {"starting", "running", "paused", "stopping"} or (
                state.phase == "failed" and state.active_job_id is not None
            ):
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute(
                        "UPDATE jobs SET status='failed', last_error=?, updated_at=? "
                        "WHERE job_id=? AND status='running'",
                        (
                            "Worker interrupted; side effects may exist. Explicit retry required.",
                            timestamp(),
                            state.active_job_id,
                        ),
                    )
                self.save(
                    state.model_copy(
                        update={
                            "phase": "interrupted",
                            "error": "Process exited before its next checkpoint; "
                            "explicit retry required for interrupted work.",
                            "heartbeat_at": timestamp(),
                        }
                    )
                )
