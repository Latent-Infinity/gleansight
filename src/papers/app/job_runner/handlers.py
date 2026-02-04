from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from papers.app import ports
from papers.app.observability import MetricsSink, NoopMetrics
from papers.domain.errors import ErrorCode, NotFoundError, NotReadyError, PipelineError
from papers.domain.models import PipelineStage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandlerContext:
    paper_store: ports.PaperStore
    job_queue: ports.JobQueue
    blob_store: ports.BlobStore
    converter: ports.Converter
    embedder: ports.Embedder
    vector_index: ports.VectorIndex
    llm_client: ports.LLMClient
    prompt_store: ports.PromptStore
    profile_store: ports.ProfileStore
    analysis_store: ports.AnalysisRunStore
    metrics: MetricsSink = field(default_factory=NoopMetrics)
    # Optional PDF resolution dependencies
    pdf_resolver: ports.PdfResolver | None = None
    pdf_downloader: ports.PdfDownloader | None = None
    external_id_store: ports.PaperExternalIdStore | None = None


@dataclass(frozen=True)
class HandlerResult:
    status: str
    error: str | None = None
    error_code: str | None = None
    retry_after: datetime | None = None

    @staticmethod
    def succeeded() -> HandlerResult:
        return HandlerResult(status="succeeded")

    @staticmethod
    def retryable(error: str, delay_s: int = 60, error_code: str | None = None) -> HandlerResult:
        return HandlerResult(
            status="retryable",
            error=error,
            error_code=error_code,
            retry_after=datetime.now() + timedelta(seconds=delay_s),
        )

    @staticmethod
    def failed(error: str, error_code: str | None = None) -> HandlerResult:
        return HandlerResult(status="failed", error=error, error_code=error_code)

    @staticmethod
    def canceled() -> HandlerResult:
        return HandlerResult(status="canceled")


def _check_cancelled(job: ports.Job, ctx: HandlerContext) -> HandlerResult | None:
    if ctx.job_queue.is_cancelled(job.job_id):
        return HandlerResult.canceled()
    return None


def _conversion_failure_result(error_code: str | None, error_message: str | None) -> HandlerResult:
    message = error_message or "conversion failed"
    if error_code in {ErrorCode.CONVERTER_TIMEOUT, ErrorCode.CONVERTER_OOM}:
        return HandlerResult.retryable(message, error_code=str(error_code))
    if error_code == ErrorCode.CONVERSION_FAILED and _is_transient_error(message):
        return HandlerResult.retryable(message, error_code=str(error_code))
    return HandlerResult.failed(message, error_code=str(error_code) if error_code else None)


def _is_transient_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "timeout",
            "temporar",
            "retry",
            "connection",
            "network",
            "unavailable",
        )
    )


def handle_download(job: ports.Job, ctx: HandlerContext) -> HandlerResult:
    """Handle download job by resolving PDF URL and downloading.

    Downloads PDF either from:
    1. Local source_path (legacy, for manual imports)
    2. Resolved URL from external IDs (ArXiv, DOI via Unpaywall)

    External IDs are retrieved from job payload or external_id_store.
    """
    if job.paper_id is None:
        return HandlerResult.failed("paper_id is required")
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled

    # Check for local source_path (legacy path)
    if "source_path" in job.payload:
        source_path = Path(job.payload["source_path"])
        pdf_xxh64, _ = ctx.blob_store.put_pdf(source_path)
        cancelled = _check_cancelled(job, ctx)
        if cancelled is not None:
            return cancelled
        ctx.paper_store.set_pdf_fingerprint(job.paper_id, pdf_xxh64)
        ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.downloaded)
        ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
        return HandlerResult.succeeded()

    # Need PDF resolver and downloader for URL-based download
    if ctx.pdf_resolver is None or ctx.pdf_downloader is None:
        return HandlerResult.failed(
            "PDF resolver not configured; cannot download without source_path",
            error_code=str(ErrorCode.NO_OPEN_PDF),
        )

    # Get external IDs from payload or store
    external_ids: dict[str, str] = job.payload.get("external_ids", {})
    if not external_ids and ctx.external_id_store is not None:
        external_ids = ctx.external_id_store.get_external_ids(job.paper_id)

    if not external_ids:
        return HandlerResult.failed(
            "No external IDs available to resolve PDF URL",
            error_code=str(ErrorCode.NO_OPEN_PDF),
        )

    # Resolve PDF URL
    resolved = ctx.pdf_resolver.resolve(external_ids)
    if resolved is None:
        return HandlerResult.failed(
            f"Could not resolve PDF URL from external IDs: {list(external_ids.keys())}",
            error_code=str(ErrorCode.NO_OPEN_PDF),
        )

    logger.info("Resolved PDF URL for paper %s: %s (source: %s)", job.paper_id, resolved.url, resolved.source)

    # Download to temp file
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled

    # Create temp file path
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        ctx.pdf_downloader.download(resolved.url, tmp_path)
    except PipelineError as e:
        # Clean up temp file on error
        if tmp_path.exists():
            tmp_path.unlink()
        # Map pipeline errors to handler results
        if e.code in {ErrorCode.TIMEOUT, ErrorCode.RATE_LIMITED, ErrorCode.NETWORK_ERROR}:
            delay_s = 60 if e.code == ErrorCode.RATE_LIMITED else 30
            return HandlerResult.retryable(str(e), delay_s=delay_s, error_code=str(e.code))
        return HandlerResult.failed(str(e), error_code=str(e.code))

    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        if tmp_path.exists():
            tmp_path.unlink()
        return cancelled

    # Store PDF in blob store
    try:
        pdf_xxh64, _ = ctx.blob_store.put_pdf(tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    ctx.paper_store.set_pdf_fingerprint(job.paper_id, pdf_xxh64)
    ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.downloaded)
    ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
    return HandlerResult.succeeded()


def handle_convert(job: ports.Job, ctx: HandlerContext) -> HandlerResult:
    if job.paper_id is None:
        return HandlerResult.failed("paper_id is required")
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    paper = ctx.paper_store.get(job.paper_id)
    if paper is None:
        raise NotFoundError("paper not found")
    pdf_fingerprint = paper.get("pdf_fingerprint_xxh64")
    if not pdf_fingerprint:
        raise NotReadyError("paper has no PDF fingerprint")
    pdf_path = ctx.blob_store.get_pdf_path(pdf_fingerprint)
    if pdf_path is None:
        raise NotFoundError("PDF blob not found")
    result = ctx.converter.pdf_to_markdown(pdf_path)
    if not result.ok:
        return _conversion_failure_result(result.error_code, result.error_message)
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    md_path, md_xxh64 = ctx.blob_store.put_markdown(job.paper_id, result.markdown or "")
    ctx.paper_store.set_markdown_provenance(
        job.paper_id,
        md_xxh64,
        pdf_fingerprint,
        converter="docling",
        converter_version=ctx.converter.version(),
    )
    ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.converted)
    ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
    return HandlerResult.succeeded()


def handle_embed(job: ports.Job, ctx: HandlerContext) -> HandlerResult:
    if job.paper_id is None:
        return HandlerResult.failed("paper_id is required")
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    paper = ctx.paper_store.get(job.paper_id)
    if paper is None:
        raise NotFoundError("paper not found")
    md_path = ctx.blob_store.get_markdown_path(job.paper_id)
    if md_path is None:
        raise NotReadyError("paper has no markdown")
    text = md_path.read_text(encoding="utf-8")
    embedding = ctx.embedder.embed(text)
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    ctx.vector_index.upsert(job.paper_id, embedding)
    md_fingerprint = paper.get("md_fingerprint_xxh64")
    if not md_fingerprint:
        raise NotReadyError("paper has no markdown fingerprint")
    ctx.paper_store.set_embedding_state(
        job.paper_id,
        ctx.embedder.model_name(),
        ctx.embedder.dimension(),
        "markdown_full",
        md_fingerprint,
    )
    ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.embedded)
    ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
    return HandlerResult.succeeded()


def handle_analyze(job: ports.Job, ctx: HandlerContext) -> HandlerResult:
    if job.paper_id is None or job.run_id is None:
        return HandlerResult.failed("paper_id and run_id are required")
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    prompt_version = ctx.prompt_store.get_version(job.payload["prompt_version_id"])
    if prompt_version is None:
        raise NotFoundError("prompt version not found")
    profile = ctx.profile_store.get(job.payload["profile_id"])
    if profile is None:
        raise NotFoundError("profile not found")
    ctx.analysis_store.mark_started(job.run_id)
    response = ctx.llm_client.complete(
        prompt=prompt_version["body"],
        profile=profile,
        model=job.payload["model_name"],
    )
    ctx.metrics.observe(
        "llm_tokens_in",
        float(response.tokens_in or 0),
        {
            "prompt_version_id": prompt_version["prompt_version_id"],
            "model_name": job.payload["model_name"],
        },
    )
    ctx.metrics.observe(
        "llm_tokens_out",
        float(response.tokens_out or 0),
        {
            "prompt_version_id": prompt_version["prompt_version_id"],
            "model_name": job.payload["model_name"],
        },
    )
    if response.cost_usd is not None:
        ctx.metrics.observe(
            "llm_cost_usd",
            float(response.cost_usd),
            {
                "prompt_version_id": prompt_version["prompt_version_id"],
                "model_name": job.payload["model_name"],
            },
        )
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    meta = {
        "run_id": job.run_id,
        "paper_id": job.paper_id,
        "prompt": {
            "prompt_id": prompt_version["prompt_id"],
            "prompt_version_id": prompt_version["prompt_version_id"],
            "version": prompt_version["version"],
            "output_format": prompt_version["output_format"],
        },
        "endpoint": {
            "profile_name": profile["name"],
            "base_url": profile["base_url"],
            "model_name": job.payload["model_name"],
        },
        "input_provenance": {
            "md_fingerprint_xxh64": "unknown",
            "md_converter": "docling",
            "md_converter_version": ctx.converter.version(),
        },
        "timing": {
            "started_at": datetime.now().isoformat(),
            "finished_at": datetime.now().isoformat(),
            "duration_ms": 0,
        },
    }
    artifacts = ctx.blob_store.put_analysis_artifacts(job.run_id, response.text, None, meta)
    ctx.analysis_store.mark_finished(
        job.run_id,
        output_md=str(artifacts["output_md"]),
        output_json=None,
        validation_issues_json=None,
        error_message=None,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        cost_usd=response.cost_usd,
    )
    ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.analyzed)
    return HandlerResult.succeeded()


HANDLERS: dict[str, Any] = {
    "download": handle_download,
    "convert": handle_convert,
    "embed": handle_embed,
    "analyze": handle_analyze,
}
