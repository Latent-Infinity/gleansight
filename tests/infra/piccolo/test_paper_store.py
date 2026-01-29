from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.domain.errors import InvalidStateTransition
from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloPaperStore


def _setup_store(tmp_path: Path) -> PiccoloPaperStore:
    db = PiccoloDatabase(tmp_path / "papers.sqlite")
    db.initialize_schema()
    return PiccoloPaperStore()


def test_create_and_get_paper(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    paper_id = "paper-1"
    store.create_paper(
        {
            "paper_id": paper_id,
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    paper = store.get(paper_id)
    assert paper is not None
    assert paper["title"] == "Title"


def test_stage_cannot_regress(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    paper_id = "paper-2"
    store.create_paper(
        {
            "paper_id": paper_id,
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    with pytest.raises(InvalidStateTransition):
        store.advance_pipeline_stage_monotonic(paper_id, PipelineStage.downloaded)


def test_set_markdown_provenance(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    paper_id = "paper-3"
    store.create_paper(
        {
            "paper_id": paper_id,
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    store.set_markdown_provenance(paper_id, "md", "pdf", "docling", "1.0")
    paper = store.get(paper_id)
    assert paper is not None
    assert paper["md_fingerprint_xxh64"] == "md"
