from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.job_runner.handlers import handle_analyze
from papers.app.observability import InMemoryMetrics
from papers.app.ports import LLMResponse
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


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        return LLMResponse(text='{"result": "ok"}', tokens_in=4, tokens_out=7, cost_usd=0.12)


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


def _context(tmp_path: Path, db: PiccoloDatabase, metrics: InMemoryMetrics) -> HandlerContext:
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
        metrics=metrics,
    )


def test_metrics_emitted_for_retryable_failure(tmp_path: Path) -> None:
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

    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf")
    pdf_fingerprint, _ = blob_store.put_pdf(pdf_path)
    paper_store.set_pdf_fingerprint("paper", pdf_fingerprint)

    metrics = InMemoryMetrics()
    ctx = _context(tmp_path, db, metrics)
    ctx = HandlerContext(
        paper_store=ctx.paper_store,
        job_queue=ctx.job_queue,
        blob_store=blob_store,
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=ctx.llm_client,
        prompt_store=ctx.prompt_store,
        profile_store=ctx.profile_store,
        analysis_store=ctx.analysis_store,
        metrics=metrics,
    )

    queue = PiccoloJobQueue()
    queue.enqueue("convert", "paper", None, {})
    runner = JobRunner(job_queue=queue, context=ctx)
    assert runner.run_next(datetime.now(UTC)) is True

    assert any(name == "job_retries_total" for name, _, _ in metrics.increments)
    assert any(name == "job_duration_ms" for name, _, _ in metrics.observations)


def test_metrics_emitted_for_llm_usage(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    metrics = InMemoryMetrics()
    ctx = _context(tmp_path, db, metrics)

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

    job = _Job(
        job_id="job",
        type="analyze",
        status="running",
        paper_id="paper",
        run_id="run",
        payload={"prompt_version_id": "pv1", "profile_id": "profile", "model_name": "model"},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )

    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=PiccoloJobQueue(),
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=ctx.converter,
        embedder=ctx.embedder,
        vector_index=ctx.vector_index,
        llm_client=_LLM(),
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
        metrics=metrics,
    )

    result = handle_analyze(job, ctx)
    assert result.status == "succeeded"

    metric_names = {name for name, _, _ in metrics.observations}
    assert "llm_tokens_in" in metric_names
    assert "llm_tokens_out" in metric_names
    assert "llm_cost_usd" in metric_names


class _SuccessConverter:
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


def test_metrics_emitted_for_successful_job(tmp_path: Path) -> None:
    """A successful job emits job_succeeded_total and job_duration_ms."""
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

    # Provide a valid local PDF so download succeeds
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf")

    metrics = InMemoryMetrics()
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=PiccoloJobQueue(),
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=_SuccessConverter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
        metrics=metrics,
    )

    queue = PiccoloJobQueue()
    queue.enqueue("download", "paper", None, {"source_path": str(pdf_path)})
    runner = JobRunner(job_queue=queue, context=ctx)
    assert runner.run_next(datetime.now(UTC)) is True

    # Verify success metrics were emitted
    succeeded_increments = [
        (name, tags) for name, _, tags in metrics.increments if name == "job_succeeded_total"
    ]
    assert succeeded_increments, "Expected job_succeeded_total increment"
    assert succeeded_increments[0][1]["job_type"] == "download"

    duration_observations = [
        (name, tags) for name, _, tags in metrics.observations if name == "job_duration_ms"
    ]
    assert duration_observations, "Expected job_duration_ms observation"
    assert duration_observations[0][1]["job_type"] == "download"

    transition_increments = [
        (name, tags) for name, _, tags in metrics.increments if name == "job_transitions_total"
    ]
    assert transition_increments, "Expected job_transitions_total increments"
    assert any(
        tags.get("status_from") == "queued" and tags.get("status_to") == "running"
        for _, tags in transition_increments
    )
