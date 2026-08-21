from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
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


def test_job_without_registered_handler_is_failed(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()
    job_id = queue.enqueue("download", "paper", None, {})
    runner = JobRunner(job_queue=queue, context=_context(tmp_path, db))
    with patch("papers.app.job_runner.runner.HANDLERS", {}):
        assert runner.run_next(datetime.now(UTC)) is True
    row = db.fetchone("SELECT status FROM jobs WHERE job_id = ?", [job_id])
    assert row is not None
    assert row["status"] == "failed"


def test_cancelled_job_returns_false(tmp_path: Path) -> None:
    """Cancelled jobs are not claimable, so run_next returns False."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()
    job_id = queue.enqueue("download", "paper", None, {"source_path": "/tmp/test.pdf"})
    queue.cancel(job_id)
    runner = JobRunner(job_queue=queue, context=_context(tmp_path, db))
    assert runner.run_next(datetime.now(UTC)) is False


def test_retryable_job_marked_correctly(tmp_path: Path) -> None:
    """Test that retryable results are handled correctly."""
    from datetime import timedelta

    from papers.app.job_runner.handlers import HandlerResult

    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()

    # Create a simple job
    job_id = queue.enqueue("download", "paper", None, {"source_path": "/tmp/test.pdf"})

    # First claim the job so it moves from queued to running
    job = queue.claim_next(datetime.now(UTC))
    assert job is not None
    assert job.job_id == job_id

    context = _context(tmp_path, db)
    runner = JobRunner(job_queue=queue, context=context)

    # Test the finalize method with a retryable result
    retry_time = datetime.now(UTC) + timedelta(seconds=60)
    retryable_result = HandlerResult(
        status="retryable",
        error="temporary error",
        retry_after=retry_time,
    )
    runner._finalize(job, retryable_result, datetime.now(UTC))

    # Check that the job was marked as retryable (queued with error and run_after)
    row = db.fetchone(f"SELECT status, last_error, run_after FROM jobs WHERE job_id = '{job_id}'")
    assert row is not None
    assert row["status"] == "queued"  # Retryable jobs are queued to run again
    assert row["last_error"] is not None
    assert "temporary error" in row["last_error"]
    assert row["run_after"] is not None  # Should have a run_after time set


def test_failed_job_marked_correctly(tmp_path: Path) -> None:
    """Test that failed results are handled correctly."""
    from papers.app.job_runner.handlers import HandlerResult

    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()
    job_id = queue.enqueue("download", "paper", None, {"source_path": "/tmp/test.pdf"})

    # First claim the job so it moves from queued to running
    job = queue.claim_next(datetime.now(UTC))
    assert job is not None
    assert job.job_id == job_id

    context = _context(tmp_path, db)
    runner = JobRunner(job_queue=queue, context=context)

    # Test the finalize method with a failed result
    failed_result = HandlerResult(status="failed", error="permanent error", retry_after=None)
    runner._finalize(job, failed_result, datetime.now(UTC))

    # Check that the job was marked as failed
    row = db.fetchone(f"SELECT status, last_error FROM jobs WHERE job_id = '{job_id}'")
    assert row is not None
    assert row["status"] == "failed"
    assert row["last_error"] is not None
    assert "permanent error" in row["last_error"]


def test_download_provenance_is_forwarded_to_convert(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    queue = PiccoloJobQueue()
    queue.enqueue(
        "download",
        "paper",
        None,
        {"source_path": "/tmp/source.pdf", "external_ids": {"ArXiv": "2401.00001"}},
    )
    download = queue.claim_next(datetime.now(UTC))
    assert download is not None

    runner = JobRunner(job_queue=queue, context=_context(tmp_path, db))
    runner._enqueue_next_step(download)

    convert = queue.claim_next(datetime.now(UTC))
    assert convert is not None
    assert convert.type == "convert"
    assert convert.payload == {
        "source_path": "/tmp/source.pdf",
        "external_ids": {"ArXiv": "2401.00001"},
    }
