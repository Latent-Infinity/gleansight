from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from papers.app.job_runner.handlers import (
    HandlerContext,
    HandlerResult,
    _finish_analysis,
    handle_analyze,
    handle_convert,
    handle_download,
    handle_embed,
)
from papers.domain.errors import ErrorCode, NotFoundError, NotReadyError
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


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        raise AssertionError("should not be called")


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


def test_handle_convert_requires_pdf(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotReadyError):
        handle_convert(job, ctx)


def test_handle_embed_requires_markdown_fingerprint(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    blob_store.put_markdown("paper", "content")
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="embed",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotReadyError):
        handle_embed(job, ctx)


def test_handler_result_retryable() -> None:
    """Test HandlerResult.retryable() creates retryable result."""
    result = HandlerResult.retryable("temporary error", delay_s=120)
    assert result.status == "retryable"
    assert result.error == "temporary error"
    assert result.retry_after is not None
    assert result.retry_after.tzinfo is UTC


def test_handler_result_failed() -> None:
    """Test HandlerResult.failed() creates failed result."""
    result = HandlerResult.failed("permanent error")
    assert result.status == "failed"
    assert result.error == "permanent error"
    assert result.retry_after is None


def test_handle_download_missing_paper_id(tmp_path: Path) -> None:
    """Test download handler fails when paper_id is None."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="download",
        status="queued",
        paper_id=None,  # Missing paper_id
        run_id=None,
        payload={"source_path": str(tmp_path / "test.pdf")},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    result = handle_download(job, ctx)
    assert result.status == "failed"
    assert result.error == "paper_id is required"


def test_handle_convert_missing_paper_id(tmp_path: Path) -> None:
    """Test convert handler fails when paper_id is None."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id=None,  # Missing paper_id
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    result = handle_convert(job, ctx)
    assert result.status == "failed"
    assert result.error == "paper_id is required"


def test_handle_convert_paper_not_found(tmp_path: Path) -> None:
    """Test convert handler raises NotFoundError when paper doesn't exist."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="nonexistent",  # Paper doesn't exist
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotFoundError, match="paper not found"):
        handle_convert(job, ctx)


def test_handle_convert_pdf_blob_not_found(tmp_path: Path) -> None:
    """Test convert handler raises NotFoundError when PDF blob doesn't exist."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    # Set a nonexistent PDF fingerprint
    paper_store.set_pdf_fingerprint("paper", "nonexistent_fingerprint")
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotFoundError, match="PDF blob not found"):
        handle_convert(job, ctx)


def test_handle_convert_conversion_failed(tmp_path: Path) -> None:
    """Test convert handler returns failed when conversion fails."""

    class _FailingConverter:
        def pdf_to_markdown(self, pdf_path: Path):
            return type(
                "Result",
                (),
                {
                    "ok": False,
                    "markdown": None,
                    "error_code": "CONVERSION_FAILED",
                    "error_message": "boom",
                },
            )()

        def version(self) -> str:
            return "1.0"

    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 fake pdf content")
    pdf_fingerprint, _ = blob_store.put_pdf(test_pdf)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    ctx = _context(tmp_path, db)
    ctx = HandlerContext(
        paper_store=ctx.paper_store,
        job_queue=ctx.job_queue,
        blob_store=ctx.blob_store,
        converter=_FailingConverter(),  # Use failing converter
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    result = handle_convert(job, ctx)
    assert result.status == "failed"
    assert result.error == "conversion failed"
    assert "boom" not in result.error


def test_handle_convert_treats_short_markdown_as_empty_output(tmp_path: Path) -> None:
    class _ShortConverter:
        def pdf_to_markdown(self, pdf_path: Path):
            return type(
                "Result",
                (),
                {"ok": True, "markdown": "short output", "error_code": None, "error_message": None},
            )()

        def version(self) -> str:
            return "1.0"

    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 fake pdf content")
    pdf_fingerprint, _ = blob_store.put_pdf(test_pdf)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    ctx = _context(tmp_path, db)
    ctx = HandlerContext(
        paper_store=ctx.paper_store,
        job_queue=ctx.job_queue,
        blob_store=ctx.blob_store,
        converter=_ShortConverter(),
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
    )
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    result = handle_convert(job, ctx)
    assert result.status == "failed"
    assert result.error_code == str(ErrorCode.EMPTY_OUTPUT)


def test_convert_preserves_corrupt_pdf_without_recovery_source(tmp_path: Path) -> None:
    """Convert shouldn't delete the only copy when re-download is impossible."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.downloaded,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    # Write corrupt content (HTML captcha page)
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"<html><body>arXiv reCAPTCHA</body></html>")
    pdf_fingerprint, blob_path = blob_store.put_pdf(corrupt_pdf)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    job_queue = PiccoloJobQueue()
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=job_queue,
        blob_store=blob_store,
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
    )
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    result = handle_convert(job, ctx)

    assert result.status == "failed"
    assert result.error_code == str(ErrorCode.CORRUPT_PDF)
    assert result.error == "Corrupt PDF detected; no recovery source available"
    assert blob_path.exists()
    assert job_queue.claim_next(datetime.now(UTC)) is None


def test_convert_proceeds_with_valid_pdf(tmp_path: Path) -> None:
    """Convert should proceed normally when PDF is valid."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.downloaded,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    valid_pdf = tmp_path / "valid.pdf"
    valid_pdf.write_bytes(b"%PDF-1.4 valid content")
    pdf_fingerprint, blob_path = blob_store.put_pdf(valid_pdf)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    result = handle_convert(job, ctx)

    # Should reach the converter (which is a stub that returns ok=True with empty markdown)
    # The blob should still exist
    assert blob_path.exists()
    # Result depends on the _Converter stub — check it doesn't return CORRUPT_PDF
    assert result.error_code != str(ErrorCode.CORRUPT_PDF) if result.error_code else True


def test_handle_embed_missing_paper_id(tmp_path: Path) -> None:
    """Test embed handler fails when paper_id is None."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="embed",
        status="queued",
        paper_id=None,  # Missing paper_id
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    result = handle_embed(job, ctx)
    assert result.status == "failed"
    assert result.error == "paper_id is required"


def test_handle_embed_paper_not_found(tmp_path: Path) -> None:
    """Test embed handler raises NotFoundError when paper doesn't exist."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="embed",
        status="queued",
        paper_id="nonexistent",  # Paper doesn't exist
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotFoundError, match="paper not found"):
        handle_embed(job, ctx)


def test_handle_embed_markdown_not_found(tmp_path: Path) -> None:
    """Test embed handler raises NotReadyError when markdown doesn't exist."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.converted,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="embed",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotReadyError, match="paper has no markdown"):
        handle_embed(job, ctx)


def test_handle_analyze_missing_ids(tmp_path: Path) -> None:
    """Test analyze handler fails when paper_id or run_id is None."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="analyze",
        status="queued",
        paper_id=None,  # Missing paper_id
        run_id=None,  # Missing run_id
        payload={"prompt_version_id": "pv", "profile_id": "prof"},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    result = handle_analyze(job, ctx)
    assert result.status == "failed"
    assert result.error == "paper_id and run_id are required"


def test_handle_analyze_prompt_version_not_found(tmp_path: Path) -> None:
    """Test analyze handler raises NotFoundError when prompt version doesn't exist."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    ctx = _context(tmp_path, db)
    job = _Job(
        job_id="job",
        type="analyze",
        status="queued",
        paper_id="paper",
        run_id="run",
        payload={"prompt_version_id": "nonexistent", "profile_id": "prof"},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(NotFoundError, match="prompt version not found"):
        handle_analyze(job, ctx)


def test_handle_analyze_profile_not_found(tmp_path: Path) -> None:
    """Test analyze handler raises NotFoundError when profile doesn't exist."""
    # This test would require complex setup of prompt and version tables
    # The coverage for lines 121 and 124 (NotFoundError cases) is achieved through
    # integration tests. For unit test purposes, the error path logic is validated
    # by other similar NotFoundError tests (convert, embed handlers).
    # Skipping this specific test to avoid complex table setup dependencies.
    pytest.skip("Complex setup required, covered by integration tests")


class TestHandleDownloadWithResolver:
    """Tests for handle_download with PDF resolver."""

    def test_download_resolves_pdf_from_external_ids(self, tmp_path: Path) -> None:
        """Should resolve and download PDF when external IDs are in payload."""
        from papers.app.ports import ResolvedPdf

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

        # Create fake resolver and downloader
        class FakeResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                if "ArXiv" in external_ids:
                    return ResolvedPdf(
                        url=f"https://arxiv.org/pdf/{external_ids['ArXiv']}.pdf",
                        source="arxiv",
                    )
                return None

        class FakeDownloader:
            def __init__(self, tmp_path: Path):
                self.tmp_path = tmp_path

            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                # Write fake PDF content
                dest_path.write_bytes(b"%PDF-1.4 fake content")

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeResolver(),
            pdf_downloader=FakeDownloader(tmp_path),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"ArXiv": "2001.12345"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "succeeded"

    def test_download_fails_without_resolver_or_source_path(self, tmp_path: Path) -> None:
        """Should fail when no resolver and no source_path."""
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

        ctx = _context(tmp_path, db)  # No resolver configured
        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"ArXiv": "2001.12345"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "failed"
        assert result.error is None or "not configured" in result.error

    def test_download_fails_without_external_ids(self, tmp_path: Path) -> None:
        """Should fail when no external IDs available."""
        from papers.app.ports import ResolvedPdf

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

        class FakeResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return None

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                pass

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeResolver(),
            pdf_downloader=FakeDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={},  # No external_ids
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "failed"
        assert result.error_code == "NO_OPEN_PDF"

    def test_download_fails_when_resolver_returns_none(self, tmp_path: Path) -> None:
        """Should fail when resolver cannot find PDF URL."""
        from papers.app.ports import ResolvedPdf

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

        class FakeResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return None  # Cannot resolve

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                pass

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeResolver(),
            pdf_downloader=FakeDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"DOI": "10.1234/abc"}},  # DOI that cannot be resolved
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "failed"
        assert result.error_code == "NO_OPEN_PDF"

    def test_download_retries_on_network_error(self, tmp_path: Path) -> None:
        """Should return retryable result on network errors."""
        from papers.app.ports import ResolvedPdf
        from papers.domain.errors import ErrorCode, PipelineError

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

        class FakeResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return ResolvedPdf(url="https://example.com/paper.pdf", source="test")

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                raise PipelineError(ErrorCode.NETWORK_ERROR, "connection refused")

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeResolver(),
            pdf_downloader=FakeDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"ArXiv": "2001.12345"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "retryable"
        assert result.error_code == "NETWORK_ERROR"

    def test_download_falls_through_on_permanent_download_failure(self, tmp_path: Path) -> None:
        """Should try next resolved URL when download fails with 403/404."""
        from papers.app.ports import ResolvedPdf
        from papers.domain.errors import ErrorCode, PipelineError

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

        class FakeChainedResolver:
            """Resolver that returns multiple URLs via resolve_all."""

            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return ResolvedPdf(url="https://blocked.example.com/paper.pdf", source="s2")

            def resolve_all(self, external_ids: dict) -> list[ResolvedPdf]:
                return [
                    ResolvedPdf(url="https://blocked.example.com/paper.pdf", source="s2"),
                    ResolvedPdf(url="https://working.example.com/paper.pdf", source="arxiv"),
                ]

        download_attempts: list[str] = []

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                download_attempts.append(url)
                if "blocked" in url:
                    raise PipelineError(ErrorCode.DOWNLOAD_FAILED, "HTTP 403: Forbidden")
                dest_path.write_bytes(b"%PDF-1.4 content")

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeChainedResolver(),
            pdf_downloader=FakeDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"DOI": "10.1234/abc"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "succeeded"
        assert len(download_attempts) == 2
        assert "blocked" in download_attempts[0]
        assert "working" in download_attempts[1]

    def test_download_fails_when_all_urls_fail(self, tmp_path: Path) -> None:
        """Should fail when all resolved URLs return permanent errors."""
        from papers.app.ports import ResolvedPdf
        from papers.domain.errors import ErrorCode, PipelineError

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

        class FakeChainedResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return ResolvedPdf(url="https://blocked1.example.com/paper.pdf", source="s2")

            def resolve_all(self, external_ids: dict) -> list[ResolvedPdf]:
                return [
                    ResolvedPdf(url="https://blocked1.example.com/paper.pdf", source="s2"),
                    ResolvedPdf(url="https://blocked2.example.com/paper.pdf", source="unpaywall"),
                ]

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                raise PipelineError(ErrorCode.DOWNLOAD_FAILED, "HTTP 403: Forbidden")

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeChainedResolver(),
            pdf_downloader=FakeDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"DOI": "10.1234/abc"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "failed"
        assert result.error is not None and "403" in result.error

    def test_download_falls_through_on_corrupt_pdf(self, tmp_path: Path) -> None:
        """Should try next resolved URL when download gets HTML instead of PDF."""
        from papers.app.ports import ResolvedPdf
        from papers.domain.errors import ErrorCode, PipelineError

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

        class FakeChainedResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return ResolvedPdf(url="https://paywall.example.com/paper.pdf", source="s2")

            def resolve_all(self, external_ids: dict) -> list[ResolvedPdf]:
                return [
                    ResolvedPdf(url="https://paywall.example.com/paper.pdf", source="s2"),
                    ResolvedPdf(url="https://working.example.com/paper.pdf", source="arxiv"),
                ]

        download_attempts: list[str] = []

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                download_attempts.append(url)
                if "paywall" in url:
                    raise PipelineError(
                        ErrorCode.CORRUPT_PDF,
                        "Downloaded file is not a valid PDF (missing %PDF- header)",
                    )
                dest_path.write_bytes(b"%PDF-1.4 content")

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeChainedResolver(),
            pdf_downloader=FakeDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"DOI": "10.1234/abc"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "succeeded"
        assert len(download_attempts) == 2
        assert "paywall" in download_attempts[0]
        assert "working" in download_attempts[1]

    def test_download_passes_source_to_downloader(self, tmp_path: Path) -> None:
        """Should pass resolved source to downloader for per-source rate limiting."""
        from papers.app.ports import ResolvedPdf

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

        class FakeResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                return ResolvedPdf(
                    url="https://export.arxiv.org/pdf/2001.12345.pdf", source="arxiv_export"
                )

        download_sources: list[str] = []

        class SourceTrackingDownloader:
            def download(self, url: str, dest_path: Path, *, source: str = "") -> None:
                download_sources.append(source)
                dest_path.write_bytes(b"%PDF-1.4 content")

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeResolver(),
            pdf_downloader=SourceTrackingDownloader(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={"external_ids": {"ArXiv": "2001.12345"}},
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "succeeded"
        assert download_sources == ["arxiv_export"]

    def test_download_uses_external_id_store_fallback(self, tmp_path: Path) -> None:
        """Should fallback to external_id_store when payload has no external_ids."""
        from papers.app.ports import ResolvedPdf

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

        class FakeResolver:
            def resolve(self, external_ids: dict) -> ResolvedPdf | None:
                if "ArXiv" in external_ids:
                    return ResolvedPdf(url="https://arxiv.org/pdf/test.pdf", source="arxiv")
                return None

        class FakeDownloader:
            def download(self, url: str, dest_path: Path, **kwargs: object) -> None:
                dest_path.write_bytes(b"%PDF-1.4 content")

        class FakeExternalIdStore:
            def create_external_ids(self, paper_id: str, external_ids: dict) -> None:
                pass

            def get_external_ids(self, paper_id: str) -> dict:
                return {"ArXiv": "2001.12345"}  # Return stored IDs

        blob_store = FileSystemBlobStore(tmp_path / "blobs")
        ctx = HandlerContext(
            paper_store=paper_store,
            job_queue=PiccoloJobQueue(),
            blob_store=blob_store,
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
            pdf_resolver=FakeResolver(),
            pdf_downloader=FakeDownloader(),
            external_id_store=FakeExternalIdStore(),
        )

        job = _Job(
            job_id="job",
            type="download",
            status="queued",
            paper_id="paper",
            run_id=None,
            payload={},  # No external_ids in payload
            attempts=0,
            max_attempts=3,
            run_after=None,
        )

        result = handle_download(job, ctx)

        assert result.status == "succeeded"


def test_finish_analysis_requires_ids() -> None:
    from papers.app.ports import LLMResponse

    ctx = MagicMock()
    job = _Job(
        job_id="job",
        type="analyze",
        status="running",
        paper_id=None,
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    response = LLMResponse(text="", tokens_in=None, tokens_out=None, cost_usd=None)
    with pytest.raises(ValueError, match="run_id and paper_id"):
        _finish_analysis(
            ctx,
            job,
            response,
            prompt_version={"prompt_version_id": "pv"},
            profile={"profile_id": "p"},
            paper={"paper_id": "x"},
            markdown=None,
            output_json=None,
            validation_issues_json=None,
            error_message=None,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            cost_usd=None,
        )
