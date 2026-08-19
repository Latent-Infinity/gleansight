from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloJobQueue,
    PiccoloPaperExternalIdStore,
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloPaperTagStore,
    PiccoloProfileStore,
    PiccoloProjectStore,
    PiccoloPromptStore,
    PiccoloTagStore,
)
from papers.infra.piccolo.tables import AnalysisRun, PaperProject, PaperTag


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
    store.advance_pipeline_stage_monotonic(paper_id, PipelineStage.downloaded)
    row = store.get(paper_id)
    assert row is not None
    assert row["pipeline_stage"] == PipelineStage.converted  # no regression


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


def test_delete_paper_removes_paper_and_related_records(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "papers.sqlite")
    db.initialize_schema()

    store = PiccoloPaperStore()
    store.create_paper(
        {
            "paper_id": "p1",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }
    )

    # Create related records
    queue = PiccoloJobQueue()
    queue.enqueue("download", "p1", None, {})

    ext_store = PiccoloPaperExternalIdStore()
    ext_store.create_external_ids("p1", {"arxiv": "1234.5678"})

    tag_store = PiccoloTagStore()
    tag_store.create_tag("tag1", "Tag 1", "topic")
    PiccoloPaperTagStore().attach("p1", "tag1")

    proj_store = PiccoloProjectStore()
    proj_store.create_project("proj1", "Project 1")
    PiccoloPaperProjectStore().attach("p1", "proj1")

    prompt_store = PiccoloPromptStore()
    prompt_store.create_prompt("prompt1", "Prompt")
    prompt_store.create_version("pv1", "prompt1", 1, "body", "json_only")
    profile_store = PiccoloProfileStore()
    profile_store.create_profile("profile1", "Local", "http://localhost")
    analysis_store = PiccoloAnalysisRunStore()
    analysis_store.create_run("run1", "p1", "pv1", "profile1", "model")

    # Delete paper
    store.delete_paper("p1")

    # Paper gone
    assert store.get("p1") is None

    # Jobs gone
    jobs = queue.list_jobs(None, 100)
    assert not any(j["paper_id"] == "p1" for j in jobs)

    # External IDs gone
    assert ext_store.get_external_ids("p1") == {}

    # Tag association gone
    tag_rows = PaperTag.select().where(PaperTag.paper_id == "p1").run_sync()
    assert tag_rows == []

    # Project association gone
    proj_rows = PaperProject.select().where(PaperProject.paper_id == "p1").run_sync()
    assert proj_rows == []

    # Analysis run gone
    run_rows = AnalysisRun.select().where(AnalysisRun.paper_id == "p1").run_sync()
    assert run_rows == []


def test_delete_paper_nonexistent_is_noop(tmp_path: Path) -> None:
    _setup_store(tmp_path)
    store = PiccoloPaperStore()
    store.delete_paper("nonexistent")  # should not raise


def test_reset_pipeline_stage(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    store.create_paper(
        {
            "paper_id": "p1",
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.error,
            "last_error_code": "CONVERTER_TIMEOUT",
            "last_error_message": "timeout",
        }
    )

    store.reset_pipeline_stage("p1", PipelineStage.imported)

    paper = store.get("p1")
    assert paper is not None
    assert paper["pipeline_stage"] == PipelineStage.imported
    assert paper["pipeline_health"] == PipelineHealth.ok
    assert paper["last_error_code"] in (None, "")
    assert paper["last_error_message"] in (None, "")
