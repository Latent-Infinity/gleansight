from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from papers.app.job_runner.handlers import HandlerContext, handle_convert
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


class _MustNotConvert:
    def pdf_to_markdown(self, pdf_path: Path):
        raise AssertionError("handler must reject invalid PDF before calling the adapter")

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


def _corrupt_context(tmp_path: Path) -> tuple[HandlerContext, PiccoloJobQueue, Path]:
    db = PiccoloDatabase(tmp_path / "corrupt.sqlite")
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
    invalid = tmp_path / "truncated.pdf"
    invalid.write_bytes(b"%PDF")
    pdf_fingerprint, blob_path = blob_store.put_pdf(invalid)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)
    job_queue = PiccoloJobQueue()
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=job_queue,
        blob_store=blob_store,
        converter=_MustNotConvert(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
    )
    return ctx, job_queue, blob_path


def test_invalid_pdf_header_fails_corrupt_and_enqueues_download(tmp_path: Path) -> None:
    ctx, job_queue, blob_path = _corrupt_context(tmp_path)
    job = _Job(
        job_id="job",
        type="convert",
        status="queued",
        paper_id="paper",
        run_id=None,
        payload={"external_ids": {"ArXiv": "2401.00001"}},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    result = handle_convert(job, ctx)

    assert result.status == "failed"
    assert result.error_code == str(ErrorCode.CORRUPT_PDF)
    assert not blob_path.exists()
    download_job = job_queue.claim_next(datetime.now(UTC))
    assert download_job is not None
    assert download_job.type == "download"
    assert download_job.paper_id == "paper"
    assert download_job.payload == {"external_ids": {"ArXiv": "2401.00001"}}
    assert job_queue.claim_next(datetime.now(UTC)) is None


def test_invalid_pdf_without_recovery_source_preserves_blob(tmp_path: Path) -> None:
    ctx, job_queue, blob_path = _corrupt_context(tmp_path)
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
