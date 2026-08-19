from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
from papers.app.use_cases.pipeline import EnqueueConvertUseCase
from papers.domain.errors import ErrorCode
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


class _RetryableConverter:
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


def test_job_logging_includes_context_fields(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
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

    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"fake pdf")

    queue = PiccoloJobQueue()
    queue.enqueue("download", "paper", None, {"source_path": str(pdf_path)})

    ctx = _context(tmp_path, db)
    runner = JobRunner(job_queue=queue, context=ctx)

    caplog.set_level(logging.INFO, logger="papers.job_runner")
    runner.run_next(datetime.now(UTC))

    records = [record for record in caplog.records if record.name == "papers.job_runner"]
    assert records

    started = next(
        (record for record in records if getattr(record, "status_to", None) == "running"),
        None,
    )
    finished = next(
        (record for record in records if getattr(record, "status_to", None) == "succeeded"),
        None,
    )

    assert started is not None
    assert finished is not None

    first = cast(logging.LogRecord, records[0])
    for record in (started, finished):
        typed = cast(logging.LogRecord, record)
        assert getattr(typed, "job_id") == getattr(first, "job_id")
        assert getattr(typed, "job_type") == "download"
        assert getattr(typed, "paper_id") == "paper"
        assert getattr(typed, "run_id") is None
        assert getattr(typed, "status_from") is not None
        assert getattr(typed, "status_to") is not None
        assert getattr(typed, "timestamp")


def test_job_logging_warns_on_retryable_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.downloaded,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )

    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf")
    pdf_fingerprint, _ = blob_store.put_pdf(pdf_path)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    ctx = _context(tmp_path, db)
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=ctx.job_queue,
        blob_store=blob_store,
        converter=_RetryableConverter(),
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )

    queue = PiccoloJobQueue()
    queue.enqueue("convert", "paper", None, {})
    runner = JobRunner(job_queue=queue, context=ctx)

    caplog.set_level(logging.INFO, logger="papers.job_runner")
    runner.run_next(datetime.now(UTC))

    warning_records = [
        r for r in caplog.records if r.name == "papers.job_runner" and r.levelno == logging.WARNING
    ]
    assert warning_records
    retry_record = next(
        (r for r in warning_records if getattr(r, "status_to", None) == "queued"), None
    )
    assert retry_record is not None
    assert getattr(retry_record, "error_code") == str(ErrorCode.CONVERTER_TIMEOUT)


def test_job_logging_errors_on_unknown_job_type(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()
    queue.enqueue("unknown", "paper", None, {})
    runner = JobRunner(job_queue=queue, context=_context(tmp_path, db))

    caplog.set_level(logging.INFO, logger="papers.job_runner")
    runner.run_next(datetime.now(UTC))

    error_record = next(
        (
            r
            for r in caplog.records
            if r.name == "papers.job_runner"
            and r.levelno == logging.ERROR
            and getattr(r, "status_to", None) == "failed"
        ),
        None,
    )
    assert error_record is not None
    assert getattr(error_record, "error_code") == "unknown_job_type"


def test_auto_chain_logging_uses_new_job_identity(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
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

    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf")

    queue = PiccoloJobQueue()
    queue.enqueue("download", "paper", None, {"source_path": str(pdf_path)})
    runner = JobRunner(job_queue=queue, context=_context(tmp_path, db))

    caplog.set_level(logging.INFO, logger="papers.job_runner")
    runner.run_next(datetime.now(UTC))

    chain_record = next(
        (
            r
            for r in caplog.records
            if r.name == "papers.job_runner"
            and getattr(r, "status_from", None) == "new"
            and getattr(r, "status_to", None) == "queued"
            and getattr(r, "job_type", None) == "convert"
        ),
        None,
    )
    assert chain_record is not None


def test_use_case_enqueue_logging_has_transition_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Queue:
        def enqueue(
            self,
            type: str,
            paper_id: str | None,
            run_id: str | None,
            payload: dict[str, object],
            run_after: datetime | None = None,
        ) -> str:
            return "job-1"

    caplog.set_level(logging.INFO, logger="papers.use_cases")
    use_case = EnqueueConvertUseCase(job_queue=_Queue())
    use_case(paper_id="paper-1")

    record = next((r for r in caplog.records if r.name == "papers.use_cases"), None)
    assert record is not None
    assert getattr(record, "timestamp")
    assert getattr(record, "status_from") == "new"
    assert getattr(record, "status_to") == "queued"


# ---------------------------------------------------------------------------
# Handler-level logging tests
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402

from papers.app.job_runner.handlers import (  # noqa: E402
    handle_analyze,
    handle_convert,
    handle_embed,
)
from papers.app.observability import NoopMetrics  # noqa: E402


@dataclass(frozen=True)
class _FakeJob:
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload: dict[str, object]
    attempts: int
    max_attempts: int
    run_after: datetime | None


def test_handler_convert_logs_warning_on_corrupt_pdf(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Convert handler should log a WARNING when a corrupt PDF is detected."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.downloaded,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )

    # Store a corrupt (non-PDF) blob
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"NOT A PDF FILE")
    pdf_xxh64, _ = blob_store.put_pdf(bad_pdf)
    paper_store.set_pdf_fingerprint("paper", pdf_xxh64)

    ctx = _context(tmp_path, db)
    job = _FakeJob(
        job_id="j1",
        type="convert",
        status="running",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    caplog.set_level(logging.WARNING, logger="papers.app.job_runner.handlers")
    result = handle_convert(job, ctx)

    assert result.status == "failed"
    handler_warnings = [
        r
        for r in caplog.records
        if r.name == "papers.app.job_runner.handlers" and r.levelno >= logging.WARNING
    ]
    assert handler_warnings, "Expected at least one WARNING from handler for corrupt PDF"
    assert any("corrupt" in r.getMessage().lower() for r in handler_warnings)


def test_handler_embed_logs_info_on_start(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Embed handler should log INFO with paper_id context."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )

    # Set up markdown blob and fingerprint
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    md_text = "# Test Markdown\n\nSome content for embedding."
    _md_path, md_xxh64 = blob_store.put_markdown("paper", md_text)
    paper_store.set_markdown_provenance("paper", md_xxh64, "pdf_xxh64", "docling", "1.0")

    ctx = _context(tmp_path, db)
    job = _FakeJob(
        job_id="j2",
        type="embed",
        status="running",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    caplog.set_level(logging.INFO, logger="papers.app.job_runner.handlers")
    result = handle_embed(job, ctx)

    assert result.status == "succeeded"
    handler_records = [
        r
        for r in caplog.records
        if r.name == "papers.app.job_runner.handlers" and r.levelno >= logging.INFO
    ]
    assert handler_records, "Expected at least one INFO log from embed handler"
    combined = " ".join(r.getMessage() for r in handler_records)
    assert "paper" in combined.lower(), "Embed log should mention the paper_id"


def test_handler_analyze_logs_info_with_model_context(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Analyze handler should log INFO with model_name and paper_id."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )

    prompt_store = PiccoloPromptStore()
    prompt_store.create_prompt("prompt", "Prompt")
    prompt_store.create_version("pv1", "prompt", 1, "Analyze: {{title}}", "json_only")

    profile_store = PiccoloProfileStore()
    profile_store.create_profile("profile", "Local", "http://localhost")

    analysis_store = PiccoloAnalysisRunStore()
    analysis_store.create_run("run", "paper", "pv1", "profile", "test-model")

    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=PiccoloJobQueue(),
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
        metrics=NoopMetrics(),
    )

    job = _FakeJob(
        job_id="j3",
        type="analyze",
        status="running",
        paper_id="paper",
        run_id="run",
        payload={"prompt_version_id": "pv1", "profile_id": "profile", "model_name": "test-model"},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    caplog.set_level(logging.INFO, logger="papers.app.job_runner.handlers")
    handle_analyze(job, ctx)

    handler_records = [
        r
        for r in caplog.records
        if r.name == "papers.app.job_runner.handlers" and r.levelno >= logging.INFO
    ]
    assert handler_records, "Expected at least one INFO log from analyze handler"
    combined = " ".join(r.getMessage() for r in handler_records)
    assert "paper" in combined.lower(), "Analyze log should mention the paper_id"
    assert "test-model" in combined, "Analyze log should mention the model name"
