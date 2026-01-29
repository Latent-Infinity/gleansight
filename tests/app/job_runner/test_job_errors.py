from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
from papers.domain.errors import ErrorCode, PipelineError
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


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        return LLMResponse(text="analysis", tokens_in=1, tokens_out=1, cost_usd=0.0)


class _FailingLLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "bad output")


class _FailingConverter:
    def pdf_to_markdown(self, pdf_path: Path):
        return type(
            "Result",
            (),
            {
                "ok": False,
                "markdown": None,
                "error_code": ErrorCode.CONVERTER_TIMEOUT,
                "error_message": "timeout",
            },
        )()

    def version(self) -> str:
        return "1.0"


def _context(tmp_path: Path, db: PiccoloDatabase) -> HandlerContext:
    return HandlerContext(
        paper_store=PiccoloPaperStore(),
        job_queue=PiccoloJobQueue(),
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=_FailingConverter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
    )


def _seed_paper(paper_store: PiccoloPaperStore, *, stage: PipelineStage) -> None:
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": stage,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )


def test_retryable_converter_error_sets_pipeline_health(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    _seed_paper(paper_store, stage=PipelineStage.imported)

    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"fake pdf")
    pdf_fingerprint, _ = blob_store.put_pdf(pdf_path)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    queue = PiccoloJobQueue()
    queue.enqueue("convert", "paper", None, {})

    ctx = _context(tmp_path, db)
    ctx = HandlerContext(
        paper_store=ctx.paper_store,
        job_queue=queue,
        blob_store=blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    runner = JobRunner(job_queue=queue, context=ctx)

    assert runner.run_next(datetime.now(UTC)) is True
    row = db.fetchone("SELECT status, last_error, run_after FROM jobs WHERE type = 'convert'")
    assert row is not None
    assert row["status"] == "queued"
    assert "timeout" in row["last_error"]
    assert row["run_after"] is not None

    paper = db.fetchone(
        "SELECT pipeline_health, last_error_code FROM papers WHERE paper_id = 'paper'"
    )
    assert paper is not None
    assert paper["pipeline_health"] == PipelineHealth.error
    assert paper["last_error_code"] == str(ErrorCode.CONVERTER_TIMEOUT)


def test_not_ready_error_is_retryable_without_pipeline_health(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    _seed_paper(paper_store, stage=PipelineStage.converted)

    queue = PiccoloJobQueue()
    queue.enqueue("embed", "paper", None, {})

    ctx = _context(tmp_path, db)
    ctx = HandlerContext(
        paper_store=ctx.paper_store,
        job_queue=queue,
        blob_store=ctx.blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    runner = JobRunner(job_queue=queue, context=ctx)

    assert runner.run_next(datetime.now(UTC)) is True
    row = db.fetchone("SELECT status FROM jobs WHERE type = 'embed'")
    assert row is not None
    assert row["status"] == "queued"

    paper = db.fetchone(
        "SELECT pipeline_health, last_error_code FROM papers WHERE paper_id = 'paper'"
    )
    assert paper is not None
    assert paper["pipeline_health"] == PipelineHealth.ok
    assert paper["last_error_code"] in (None, "")


def test_analyze_parse_failed_is_permanent(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    _seed_paper(paper_store, stage=PipelineStage.embedded)

    prompt_store = PiccoloPromptStore()
    prompt_store.create_prompt("prompt", "Prompt")
    prompt_store.create_version("pv1", "prompt", 1, "body", "json_only")
    profile_store = PiccoloProfileStore()
    profile_store.create_profile("profile", "Local", "http://localhost")

    analysis_store = PiccoloAnalysisRunStore()
    analysis_store.create_run("run", "paper", "pv1", "profile", "model")

    queue = PiccoloJobQueue()
    queue.enqueue(
        "analyze",
        "paper",
        "run",
        {"prompt_version_id": "pv1", "profile_id": "profile", "model_name": "model"},
    )

    ctx = _context(tmp_path, db)
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=queue,
        blob_store=ctx.blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=_FailingLLM(),
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
    )
    runner = JobRunner(job_queue=queue, context=ctx)

    assert runner.run_next(datetime.now(UTC)) is True
    row = db.fetchone("SELECT status FROM jobs WHERE type = 'analyze'")
    assert row is not None
    assert row["status"] == "failed"

    paper = db.fetchone("SELECT pipeline_health FROM papers WHERE paper_id = 'paper'")
    assert paper is not None
    assert paper["pipeline_health"] == PipelineHealth.ok


@dataclass
class _FlipCancelQueue:
    base: PiccoloJobQueue
    _calls: int = 0

    def enqueue(self, *args, **kwargs):
        return self.base.enqueue(*args, **kwargs)

    def claim_next(self, now: datetime):
        return self.base.claim_next(now)

    def mark_succeeded(self, job_id: str, metrics: dict | None = None) -> None:
        self.base.mark_succeeded(job_id, metrics)

    def mark_retryable(
        self,
        job_id: str,
        error: str,
        run_after: datetime,
        metrics: dict | None = None,
    ) -> None:
        self.base.mark_retryable(job_id, error, run_after, metrics)

    def mark_failed(self, job_id: str, error: str, metrics: dict | None = None) -> None:
        self.base.mark_failed(job_id, error, metrics)

    def cancel(self, job_id: str) -> None:
        self.base.cancel(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        self._calls += 1
        if self._calls == 1:
            self.base.cancel(job_id)
            return False
        return True


def test_cooperative_cancellation_does_not_overwrite(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    _seed_paper(paper_store, stage=PipelineStage.imported)

    base_queue = PiccoloJobQueue()
    job_id = base_queue.enqueue(
        "download",
        "paper",
        None,
        {"source_path": str(tmp_path / "pdf.pdf")},
    )

    ctx = _context(tmp_path, db)
    flip_queue = _FlipCancelQueue(base=base_queue)
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=flip_queue,
        blob_store=ctx.blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    runner = JobRunner(job_queue=flip_queue, context=ctx)

    assert runner.run_next(datetime.now(UTC)) is True
    row = db.fetchone(f"SELECT status FROM jobs WHERE job_id = '{job_id}'")
    assert row is not None
    assert row["status"] == "canceled"
