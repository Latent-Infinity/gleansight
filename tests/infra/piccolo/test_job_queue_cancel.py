from __future__ import annotations

from datetime import datetime
from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloJobQueue


def test_cancel_and_is_cancelled(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "jobs.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()
    job_id = queue.enqueue("download", "paper", None, {})
    queue.cancel(job_id)
    assert queue.is_cancelled(job_id)
    assert queue.claim_next(datetime.now()) is None
