from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nsqd.infra.piccolo.stores import PiccoloNsqdJobQueue
from nsqd.ports import NSQD_JOB_TYPES
from papers.infra.piccolo.database import PiccoloDatabase


def test_discovery_jobs_persist_on_nsqd_jobs_table(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "jobs.sqlite")
    db.initialize_schema()
    queue = PiccoloNsqdJobQueue(db)
    now = datetime(2024, 6, 1, tzinfo=UTC)
    for job_type in sorted(NSQD_JOB_TYPES):
        job_id = queue.enqueue(job_type, {"k": job_type})
        row = db.fetchone("SELECT type, status FROM nsqd_jobs WHERE job_id = ?", [job_id])
        assert row is not None
        assert row["type"] == job_type
        assert row["status"] == "queued"
        claimed = queue.claim_next(now)
        assert claimed is not None
        assert claimed.job_id == job_id
        queue.mark_succeeded(job_id)
    types = {row["type"] for row in db.fetchall("SELECT type FROM nsqd_jobs")}
    assert types == NSQD_JOB_TYPES

    for job_type in sorted(NSQD_JOB_TYPES):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO jobs (
                    job_id, type, status, paper_id, run_id, payload_json,
                    attempts, max_attempts, run_after, last_error, created_at, updated_at
                ) VALUES (?, ?, 'queued', NULL, NULL, ?, 0, 3, NULL, NULL, ?, ?)
                """,
                [f"paper-{job_type}", job_type, "{}", now, now],
            )


def test_terminal_job_transitions_are_ignored_after_completion(tmp_path: Path) -> None:
    now = datetime(2024, 6, 1, tzinfo=UTC)

    canceled_db = PiccoloDatabase(tmp_path / "terminal-canceled.sqlite")
    canceled_db.initialize_schema()
    queue = PiccoloNsqdJobQueue(canceled_db)
    canceled_id = queue.enqueue("harvest", {"case": "canceled"})
    queue.cancel(canceled_id)
    queue.mark_succeeded(canceled_id)
    queue.mark_retryable(canceled_id, "late", now)
    queue.mark_failed(canceled_id, "late")
    canceled_row = canceled_db.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE job_id = ?",
        [canceled_id],
    )
    assert canceled_row is not None
    assert canceled_row["status"] == "canceled"
    assert canceled_row["last_error"] is None

    failed_db = PiccoloDatabase(tmp_path / "terminal-failed.sqlite")
    failed_db.initialize_schema()
    queue = PiccoloNsqdJobQueue(failed_db)
    failed_id = queue.enqueue("diverge", {"case": "failed"})
    failed = queue.claim_next(now)
    assert failed is not None
    assert failed.job_id == failed_id
    queue.mark_failed(failed_id, "boom")
    queue.cancel(failed_id)
    queue.mark_succeeded(failed_id)
    queue.mark_retryable(failed_id, "late", now)
    failed_row = failed_db.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE job_id = ?",
        [failed_id],
    )
    assert failed_row is not None
    assert failed_row["status"] == "failed"
    assert failed_row["last_error"] == "boom"

    succeeded_db = PiccoloDatabase(tmp_path / "terminal-succeeded.sqlite")
    succeeded_db.initialize_schema()
    queue = PiccoloNsqdJobQueue(succeeded_db)
    succeeded_id = queue.enqueue("ground", {"case": "succeeded"})
    succeeded = queue.claim_next(now)
    assert succeeded is not None
    assert succeeded.job_id == succeeded_id
    queue.mark_succeeded(succeeded_id)
    queue.cancel(succeeded_id)
    queue.mark_failed(succeeded_id, "late")
    queue.mark_retryable(succeeded_id, "late", now)
    succeeded_row = succeeded_db.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE job_id = ?",
        [succeeded_id],
    )
    assert succeeded_row is not None
    assert succeeded_row["status"] == "succeeded"
    assert succeeded_row["last_error"] is None
