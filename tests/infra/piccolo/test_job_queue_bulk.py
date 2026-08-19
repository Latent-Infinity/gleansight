from __future__ import annotations

from datetime import datetime
from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloJobQueue


def _setup_queue(tmp_path: Path) -> PiccoloJobQueue:
    db = PiccoloDatabase(tmp_path / "jobs.sqlite")
    db.initialize_schema()
    return PiccoloJobQueue()


def test_bulk_delete_removes_multiple_jobs(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    id1 = queue.enqueue("download", "p1", None, {})
    id2 = queue.enqueue("download", "p2", None, {})
    id3 = queue.enqueue("convert", "p3", None, {})

    count = queue.bulk_delete_jobs([id1, id2])

    assert count == 2
    remaining = queue.list_jobs()
    assert len(remaining) == 1
    assert remaining[0]["job_id"] == id3


def test_bulk_delete_empty_list_is_noop(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    queue.enqueue("download", "p1", None, {})

    count = queue.bulk_delete_jobs([])

    assert count == 0
    assert len(queue.list_jobs()) == 1


def test_bulk_delete_nonexistent_ids_returns_zero(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    count = queue.bulk_delete_jobs(["nonexistent-1", "nonexistent-2"])
    assert count == 0


def test_bulk_cancel_cancels_queued_jobs(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    id1 = queue.enqueue("download", "p1", None, {})
    id2 = queue.enqueue("convert", "p2", None, {})

    count = queue.bulk_cancel_jobs([id1, id2])

    assert count == 2
    assert queue.is_cancelled(id1)
    assert queue.is_cancelled(id2)


def test_bulk_cancel_skips_already_succeeded(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    id1 = queue.enqueue("download", "p1", None, {})
    queue.claim_next(datetime.now())
    queue.mark_succeeded(id1)
    id2 = queue.enqueue("convert", "p2", None, {})

    count = queue.bulk_cancel_jobs([id1, id2])

    assert count == 1
    # id1 was succeeded, cancel should not change its status
    jobs = queue.list_jobs()
    job1 = next(j for j in jobs if j["job_id"] == id1)
    assert job1["status"] == "succeeded"
    assert queue.is_cancelled(id2)


def test_bulk_cancel_running_jobs(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    id1 = queue.enqueue("download", "p1", None, {})
    queue.claim_next(datetime.now())  # now running

    count = queue.bulk_cancel_jobs([id1])

    assert count == 1
    assert queue.is_cancelled(id1)


def test_bulk_cancel_empty_list_is_noop(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    queue.enqueue("download", "p1", None, {})

    count = queue.bulk_cancel_jobs([])

    assert count == 0
    jobs = queue.list_jobs()
    assert jobs[0]["status"] == "queued"


def test_bulk_cancel_skips_already_failed(tmp_path: Path) -> None:
    queue = _setup_queue(tmp_path)
    id1 = queue.enqueue("download", "p1", None, {})
    queue.claim_next(datetime.now())
    queue.mark_failed(id1, "some error")

    count = queue.bulk_cancel_jobs([id1])

    assert count == 0
    jobs = queue.list_jobs()
    job1 = next(j for j in jobs if j["job_id"] == id1)
    assert job1["status"] == "failed"
