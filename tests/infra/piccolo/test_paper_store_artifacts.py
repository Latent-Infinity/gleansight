from __future__ import annotations

from pathlib import Path

from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloPaperStore


def test_artifact_updates(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "paper.sqlite")
    db.initialize_schema()
    store = PiccoloPaperStore()
    store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    store.set_pdf_fingerprint("paper", "pdf")
    store.set_embedding_state("paper", "model", 3, "strategy", "md")
    paper = store.get("paper")
    assert paper is not None
    assert paper["pdf_fingerprint_xxh64"] == "pdf"
    assert paper["embedding_model"] == "model"
