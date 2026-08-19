from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloJobQueue,
    PiccoloPaperStore,
    PiccoloProfileStore,
    PiccoloPromptStore,
)

pytestmark = pytest.mark.integration


class _VectorIndex:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []


class _Converter:
    def pdf_to_markdown(self, pdf_path: Path):
        return type(
            "Result",
            (),
            {
                "ok": True,
                "markdown": "This is converted markdown content. " * 6,
                "error_code": None,
                "error_message": None,
            },
        )()

    def version(self) -> str:
        return "1.0"


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        return LLMResponse(text='{"result": "ok"}', tokens_in=1, tokens_out=1, cost_usd=0.0)


def _context(tmp_path: Path, db: PiccoloDatabase) -> HandlerContext:
    return HandlerContext(
        paper_store=PiccoloPaperStore(),
        job_queue=PiccoloJobQueue(),
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
    )


def test_pipeline_end_to_end(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )

    prompt_store = PiccoloPromptStore()
    prompt_store.create_prompt("prompt", "Prompt")
    prompt_store.create_version("pv1", "prompt", 1, "body", "json_only")

    profile_store = PiccoloProfileStore()
    profile_store.create_profile("profile", "Local", "http://localhost")

    analysis_store = PiccoloAnalysisRunStore()
    analysis_store.create_run("run", "paper", "pv1", "profile", "model")

    queue = PiccoloJobQueue()

    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"fake pdf")
    queue.enqueue("download", "paper", None, {"source_path": str(pdf_path)})
    queue.enqueue("convert", "paper", None, {})
    queue.enqueue("embed", "paper", None, {})
    queue.enqueue(
        "analyze",
        "paper",
        "run",
        {"prompt_version_id": "pv1", "profile_id": "profile", "model_name": "model"},
    )

    ctx = _context(tmp_path, db)
    runner = JobRunner(job_queue=queue, context=ctx)

    while runner.run_next(datetime.now(UTC)):
        pass

    row = db.fetchone("SELECT pipeline_stage FROM papers WHERE paper_id = ?", ["paper"])
    assert row is not None
    assert row["pipeline_stage"] == PipelineStage.analyzed
