from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloPaperStore

pytestmark = pytest.mark.integration


def test_piccolo_paper_store_roundtrip(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )

    store.set_pdf_fingerprint("paper", "abc")
    store.advance_pipeline_stage_monotonic("paper", PipelineStage.downloaded)

    row = db.fetchone(
        "SELECT title, pipeline_stage, pdf_fingerprint_xxh64 FROM papers WHERE paper_id = ?",
        ["paper"],
    )
    assert row is not None
    assert row["title"] == "Title"
    assert row["pipeline_stage"] == PipelineStage.downloaded
    assert row["pdf_fingerprint_xxh64"] == "abc"
