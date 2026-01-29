from __future__ import annotations

from pathlib import Path

from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloPaperStore


def _setup_store(tmp_path: Path) -> PiccoloPaperStore:
    db = PiccoloDatabase(tmp_path / "papers.sqlite")
    db.initialize_schema()
    return PiccoloPaperStore()


def test_update_metadata_and_pipeline_health(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    paper_id = "paper"
    store.create_paper(
        {
            "paper_id": paper_id,
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    store.update_metadata(paper_id, {"title": "New", "authors": ["A"]})
    paper = store.get(paper_id)
    assert paper is not None
    assert paper["title"] == "New"
    assert paper["authors"] == ["A"]

    store.set_pipeline_health_error(paper_id, "ERR", "msg", "job")
    paper = store.get(paper_id)
    assert paper is not None
    assert paper["pipeline_health"] == PipelineHealth.error

    store.clear_pipeline_health_if_recovered(paper_id, "download")
    paper = store.get(paper_id)
    assert paper is not None
    assert paper["pipeline_health"] == PipelineHealth.ok
