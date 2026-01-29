from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloJobQueue


def _setup_queue(tmp_path: Path) -> PiccoloJobQueue:
    db = PiccoloDatabase(tmp_path / "jobs.sqlite")
    db.initialize_schema()
    return PiccoloJobQueue()


def test_enqueue_deduplicates_active_stage_jobs(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    job_id_1 = queue.enqueue("download", "paper", None, {})
    job_id_2 = queue.enqueue("download", "paper", None, {})
    assert job_id_1 == job_id_2


def test_enqueue_allows_multiple_for_different_papers(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    job_a = queue.enqueue("download", "paper-a", None, {})
    job_b = queue.enqueue("download", "paper-b", None, {})
    assert job_a != job_b


def test_claim_next_marks_running_and_increments_attempts(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    queue.enqueue("embed", "paper", None, {})
    job = queue.claim_next(datetime.now())
    assert job is not None
    assert job.status == "running"
    assert job.attempts == 1


def test_retryable_moves_job_back_to_queue(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    job_id = queue.enqueue("convert", "paper", None, {})
    job = queue.claim_next(datetime.now())
    assert job is not None
    queue.mark_retryable(job_id, "oops", datetime.now() + timedelta(seconds=60))
    next_job = queue.claim_next(datetime.now())
    assert next_job is None
