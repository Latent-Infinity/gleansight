"""Atomic job claims tied to the owning worker and resource admission rules."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from gleansight.workers.store import WorkerStore, timestamp
from papers.infra.piccolo.stores import JobRow, PiccoloJobQueue


class TokenBoundUnavailable(RuntimeError):
    """The next provider job has no enforceable token upper bound."""


class Claim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload_json: str
    attempts: int
    max_attempts: int
    run_after: datetime | None


class WorkerQueue(PiccoloJobQueue):
    def __init__(self, store: WorkerStore, worker_id: str, max_tokens: int | None) -> None:
        self.store = store
        self.worker_id = worker_id
        self.max_tokens = max_tokens

    def eligible(self) -> bool:
        with closing(sqlite3.connect(self.store.path)) as connection:
            row = connection.execute(
                "SELECT type FROM jobs WHERE status='queued' "
                "AND (run_after IS NULL OR julianday(run_after) <= julianday(?)) "
                "AND attempts < max_attempts ORDER BY created_at, job_id LIMIT 1",
                (timestamp(),),
            ).fetchone()
        if row is None:
            return False
        if self.max_tokens is not None and row[0] in {"analyze", "embed"}:
            message = "Provider token upper bound is unavailable; intake stopped before claim."
            raise TokenBoundUnavailable(message)
        return True

    def claim_next(self, now: datetime) -> JobRow | None:
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            control = connection.execute(
                "SELECT desired_state FROM supervised_workers WHERE worker_id=?", (self.worker_id,)
            ).fetchone()
            if control is None or control[0] != "run":
                return None
            row = connection.execute(
                "SELECT * FROM jobs WHERE status='queued' "
                "AND (run_after IS NULL OR julianday(run_after) <= julianday(?)) "
                "AND attempts < max_attempts ORDER BY created_at, job_id LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if row is None:
                return None
            pending = Claim.model_validate(dict(row))
            if self.max_tokens is not None and pending.type in {"analyze", "embed"}:
                message = "Provider token upper bound is unavailable; intake stopped before claim."
                raise TokenBoundUnavailable(message)
            connection.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? "
                "WHERE job_id=? AND status='queued'",
                (timestamp(), pending.job_id),
            )
            connection.execute(
                "UPDATE supervised_workers SET document_json=json_set(document_json, "
                "'$.active_job_id', ?, '$.active_run_id', ?) WHERE worker_id=?",
                (pending.job_id, pending.run_id, self.worker_id),
            )
        return JobRow(
            job_id=pending.job_id,
            type=pending.type,
            status="running",
            paper_id=pending.paper_id,
            run_id=pending.run_id,
            payload=TypeAdapter(dict[str, JsonValue]).validate_json(pending.payload_json),
            attempts=pending.attempts + 1,
            max_attempts=pending.max_attempts,
            run_after=pending.run_after,
        )

    def recorded_tokens(self, job_id: str | None, prior: int | None) -> int | None:
        with closing(sqlite3.connect(self.store.path)) as connection:
            job = connection.execute(
                "SELECT type, run_id FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job is None or job[0] == "embed":
                return None
            if job[0] != "analyze":
                return prior
            row = connection.execute(
                "SELECT tokens_in, tokens_out, output_blob_path_md "
                "FROM analysis_runs WHERE run_id=?",
                (job[1],),
            ).fetchone()
        if prior is None or row is None or row[0] is None or row[1] is None or not row[2]:
            return None
        return prior + int(row[0]) + int(row[1])
