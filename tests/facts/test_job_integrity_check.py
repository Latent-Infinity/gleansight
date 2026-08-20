from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.infra.piccolo.database import PiccoloDatabase

_NOW = datetime.now(UTC).isoformat()


def _insert_job(
    db: PiccoloDatabase,
    *,
    job_id: str,
    type: str,
    paper_id: str | None,
    run_id: str | None,
    status: str = "queued",
) -> None:
    db.execute(
        """
        INSERT INTO jobs (
            job_id, type, status, paper_id, run_id, payload_json,
            attempts, max_attempts, run_after, last_error, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            job_id,
            type,
            status,
            paper_id,
            run_id,
            "{}",
            0,
            3,
            None,
            None,
            _NOW,
            _NOW,
        ],
    )


@pytest.mark.parametrize("job_type", ["download", "convert", "embed"])
def test_stage_job_without_paper_id_is_rejected(tmp_path: Path, job_type: str) -> None:
    db = PiccoloDatabase(tmp_path / "app.sqlite")
    db.initialize_schema()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(
            db,
            job_id=f"{job_type}-null",
            type=job_type,
            paper_id=None,
            run_id=None,
        )


def test_analyze_without_run_id_is_rejected(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "app.sqlite")
    db.initialize_schema()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(db, job_id="an-null", type="analyze", paper_id="paper-1", run_id=None)


def test_discover_with_null_paper_id_is_allowed(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "app.sqlite")
    db.initialize_schema()
    _insert_job(db, job_id="disc-1", type="discover", paper_id=None, run_id=None)
    row = db.fetchone("SELECT paper_id FROM jobs WHERE job_id = ?", ["disc-1"])
    assert row is not None
    assert row["paper_id"] is None


def test_legal_stage_and_analyze_jobs_are_allowed(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "app.sqlite")
    db.initialize_schema()
    for job_type in ("download", "convert", "embed"):
        _insert_job(
            db,
            job_id=f"{job_type}-1",
            type=job_type,
            paper_id="paper-1",
            run_id=None,
        )
    _insert_job(db, job_id="an-1", type="analyze", paper_id="paper-1", run_id="run-1")
    ids = {row["job_id"] for row in db.fetchall("SELECT job_id FROM jobs")}
    assert ids == {"download-1", "convert-1", "embed-1", "an-1"}
