from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from papers.app.job_runner.handlers import (
    HandlerContext,
    handle_convert,
    handle_download,
    handle_embed,
)
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


class _VectorIndex:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []


class _Converter:
    def pdf_to_markdown(self, pdf_path: Path):
        raise AssertionError("converter should not be called")

    def version(self) -> str:
        return "1.0"


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        raise AssertionError("embed should not be called")


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        raise AssertionError("llm should not be called")


@dataclass(frozen=True)
class _Job:
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload: dict[str, object]
    attempts: int
    max_attempts: int
    run_after: datetime | None


def _context(tmp_path: Path) -> HandlerContext:
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


def test_download_noop_when_pdf_already_present(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    src = tmp_path / "paper.pdf"
    src.write_bytes(b"%PDF-1.4 noop")
    pdf_xxh64, _ = blob_store.put_pdf(src)
    paper_store.set_pdf_fingerprint("paper", pdf_xxh64)

    ctx = _context(tmp_path)
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=ctx.job_queue,
        blob_store=blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    result = handle_download(
        _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={},
            attempts=0,
            max_attempts=3,
            run_after=None,
        ),
        ctx,
    )
    assert result.status == "succeeded"


def test_convert_noop_when_matching_markdown_exists(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.downloaded,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    src = tmp_path / "paper.pdf"
    src.write_bytes(b"%PDF-1.4 noop")
    pdf_xxh64, _ = blob_store.put_pdf(src)
    paper_store.set_pdf_fingerprint("paper", pdf_xxh64)
    _md_path, md_xxh64 = blob_store.put_markdown("paper", "already converted")
    paper_store.set_markdown_provenance("paper", md_xxh64, pdf_xxh64, "docling", "1.0")

    ctx = _context(tmp_path)
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=ctx.job_queue,
        blob_store=blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    result = handle_convert(
        _Job(
            job_id="job",
            type="convert",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={},
            attempts=0,
            max_attempts=3,
            run_after=None,
        ),
        ctx,
    )
    assert result.status == "succeeded"


def test_embed_noop_when_embedding_state_matches(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.ok,
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    _md_path, md_xxh64 = blob_store.put_markdown("paper", "already embedded")
    paper_store.set_markdown_provenance("paper", md_xxh64, "pdf", "docling", "1.0")
    paper_store.set_embedding_state("paper", "model", 3, "markdown_full", md_xxh64)

    ctx = _context(tmp_path)
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=ctx.job_queue,
        blob_store=blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    result = handle_embed(
        _Job(
            job_id="job",
            type="embed",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={},
            attempts=0,
            max_attempts=3,
            run_after=None,
        ),
        ctx,
    )
    assert result.status == "succeeded"
