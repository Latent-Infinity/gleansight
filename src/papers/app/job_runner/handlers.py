from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from papers.app import ports
from papers.app.observability import MetricsSink, NoopMetrics
from papers.domain.errors import (
    ErrorCode,
    NotFoundError,
    NotReadyError,
    OutputParseFailed,
    PipelineError,
)
from papers.domain.models import OutputFormat, PipelineStage
from papers.domain.policies import (
    flatten_extractions,
    parse_llm_output,
    render_prompt_template,
    validate_extraction_output,
)

logger = logging.getLogger(__name__)

_KEYCHAIN_SERVICE_PREFIX = "paper-manager/endpoint"
_MIN_MD_CHARS = 100


def _is_valid_pdf(path: Path) -> bool:
    """Check that the file starts with the PDF magic number."""
    with path.open("rb") as f:
        header = f.read(5)
    return header.startswith(b"%PDF-")


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
    extraction_store: ports.ExtractionStore | None = None
    metrics: MetricsSink = field(default_factory=NoopMetrics)
    # Optional PDF resolution dependencies
    pdf_resolver: ports.PdfResolver | None = None
    pdf_downloader: ports.PdfDownloader | None = None
    external_id_store: ports.PaperExternalIdStore | None = None
    # Optional discover dependencies
    scholar_client: ports.ScholarClient | None = None
    candidate_store: ports.CandidateStore | None = None


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
            retry_after=datetime.now(UTC) + timedelta(seconds=delay_s),
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


def _load_profile_api_key(profile_name: str) -> str | None:
    env_key_name = f"PAPERS_ENDPOINT_API_KEY_{profile_name.upper().replace('-', '_')}"
    if env_key := os.environ.get(env_key_name):
        return env_key
    if env_key := os.environ.get("PAPERS_ENDPOINT_API_KEY"):
        return env_key
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    try:
        return keyring.get_password(f"{_KEYCHAIN_SERVICE_PREFIX}/{profile_name}", "api_key")
    except Exception:
        return None


def _profile_with_api_key(profile: dict[str, Any]) -> dict[str, Any]:
    result = dict(profile)
    if result.get("api_key"):
        return result
    profile_name = str(result.get("name") or "").strip()
    if not profile_name:
        return result
    api_key = _load_profile_api_key(profile_name)
    if api_key:
        result["api_key"] = api_key
    return result


def _calculate_run_cost(response: ports.LLMResponse, profile: dict[str, Any]) -> float | None:
    if response.cost_usd is not None:
        return float(response.cost_usd)
    if response.tokens_in is None or response.tokens_out is None:
        return None
    input_price = profile.get("input_price_per_1k_tokens")
    output_price = profile.get("output_price_per_1k_tokens")
    if input_price is None or output_price is None:
        return None
    try:
        return (float(response.tokens_in) * float(input_price) / 1000.0) + (
            float(response.tokens_out) * float(output_price) / 1000.0
        )
    except (TypeError, ValueError):
        return None


def _as_json_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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
    paper = ctx.paper_store.get(job.paper_id)
    if paper is None:
        raise NotFoundError("paper not found")

    # Idempotent no-op when a fingerprinted PDF blob already exists.
    existing_pdf_xxh64 = paper.get("pdf_fingerprint_xxh64")
    if existing_pdf_xxh64 and ctx.blob_store.get_pdf_path(existing_pdf_xxh64) is not None:
        ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.downloaded)
        ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
        return HandlerResult.succeeded()

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

    # Resolve PDF URLs — collect all candidates so we can fall through on download failure
    resolve_all = getattr(ctx.pdf_resolver, "resolve_all", None)
    if resolve_all is not None:
        resolved_list = resolve_all(external_ids)
    else:
        single = ctx.pdf_resolver.resolve(external_ids)
        resolved_list = [single] if single else []

    if not resolved_list:
        return HandlerResult.failed(
            f"Could not resolve PDF URL from external IDs: {list(external_ids.keys())}",
            error_code=str(ErrorCode.NO_OPEN_PDF),
        )

    # Try each resolved URL in turn; fall through on permanent download failures (e.g. 403)
    last_download_error: PipelineError | None = None
    for resolved in resolved_list:
        logger.info(
            "Trying PDF URL for paper %s: %s (source: %s)",
            job.paper_id,
            resolved.url,
            resolved.source,
        )

        cancelled = _check_cancelled(job, ctx)
        if cancelled is not None:
            return cancelled

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            ctx.pdf_downloader.download(resolved.url, tmp_path, source=resolved.source)
        except PipelineError as e:
            if tmp_path.exists():
                tmp_path.unlink()
            # Retryable errors (timeout, rate limit, server error) — stop and retry later
            if e.code in {ErrorCode.TIMEOUT, ErrorCode.RATE_LIMITED, ErrorCode.NETWORK_ERROR}:
                delay_s = 60 if e.code == ErrorCode.RATE_LIMITED else 30
                return HandlerResult.retryable(str(e), delay_s=delay_s, error_code=str(e.code))
            # Permanent download failure (403, 404, etc.) — try next URL
            logger.warning("Download failed for %s: %s — trying next URL", resolved.url, e)
            last_download_error = e
            continue

        # Download succeeded
        cancelled = _check_cancelled(job, ctx)
        if cancelled is not None:
            if tmp_path.exists():
                tmp_path.unlink()
            return cancelled

        try:
            pdf_xxh64, _ = ctx.blob_store.put_pdf(tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        ctx.paper_store.set_pdf_fingerprint(job.paper_id, pdf_xxh64)
        ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.downloaded)
        ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
        return HandlerResult.succeeded()

    # All URLs failed with permanent errors
    msg = str(last_download_error) if last_download_error else "all resolved URLs failed"
    code = str(last_download_error.code) if last_download_error else str(ErrorCode.DOWNLOAD_FAILED)
    return HandlerResult.failed(msg, error_code=code)


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

    converter_name = "docling"
    converter_version = ctx.converter.version()
    md_path_existing = ctx.blob_store.get_markdown_path(job.paper_id)
    if (
        paper.get("md_fingerprint_xxh64")
        and paper.get("md_source_pdf_fingerprint_xxh64") == pdf_fingerprint
        and paper.get("md_converter") == converter_name
        and paper.get("md_converter_version") == converter_version
        and md_path_existing is not None
    ):
        ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.converted)
        ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
        return HandlerResult.succeeded()

    if not _is_valid_pdf(pdf_path):
        logger.warning("Corrupt PDF detected for paper %s, enqueuing re-download", job.paper_id)
        pdf_path.unlink(missing_ok=True)
        ctx.job_queue.enqueue("download", paper_id=job.paper_id, run_id=None, payload={})
        return HandlerResult.failed(
            "Corrupt PDF detected, re-download enqueued",
            error_code=str(ErrorCode.CORRUPT_PDF),
        )
    result = ctx.converter.pdf_to_markdown(pdf_path)
    if not result.ok:
        return _conversion_failure_result(result.error_code, result.error_message)
    markdown = result.markdown or ""
    if len(markdown.strip()) < _MIN_MD_CHARS:
        return HandlerResult.failed(
            f"converted markdown shorter than minimum threshold ({_MIN_MD_CHARS} chars)",
            error_code=str(ErrorCode.EMPTY_OUTPUT),
        )
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    _md_path, md_xxh64 = ctx.blob_store.put_markdown(job.paper_id, markdown)
    ctx.paper_store.set_markdown_provenance(
        job.paper_id,
        md_xxh64,
        pdf_fingerprint,
        converter=converter_name,
        converter_version=converter_version,
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

    md_fingerprint = paper.get("md_fingerprint_xxh64")
    if not md_fingerprint:
        raise NotReadyError("paper has no markdown fingerprint")
    embedding_model = ctx.embedder.model_name()
    embedding_dimension = ctx.embedder.dimension()
    text_slice_strategy = "markdown_full"
    if (
        paper.get("embedded_from_md_fingerprint_xxh64") == md_fingerprint
        and paper.get("embedding_model") == embedding_model
        and paper.get("embedding_dimension") == embedding_dimension
        and paper.get("text_slice_strategy") == text_slice_strategy
    ):
        ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.embedded)
        ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
        return HandlerResult.succeeded()

    text = md_path.read_text(encoding="utf-8")
    logger.info("embed started for paper %s, model=%s", job.paper_id, embedding_model)
    embedding = ctx.embedder.embed(text)
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled
    ctx.vector_index.upsert(job.paper_id, embedding)
    ctx.paper_store.set_embedding_state(
        job.paper_id,
        embedding_model,
        embedding_dimension,
        text_slice_strategy,
        md_fingerprint,
    )
    ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.embedded)
    ctx.paper_store.clear_pipeline_health_if_recovered(job.paper_id, job.type)
    logger.info("embed completed for paper %s", job.paper_id)
    return HandlerResult.succeeded()


def handle_analyze(job: ports.Job, ctx: HandlerContext) -> HandlerResult:  # noqa: C901 PLR0912
    if job.paper_id is None or job.run_id is None:
        return HandlerResult.failed("paper_id and run_id are required")
    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled

    # Load prompt version, profile, and paper
    prompt_version = ctx.prompt_store.get_version(job.payload["prompt_version_id"])
    if prompt_version is None:
        raise NotFoundError("prompt version not found")
    profile = ctx.profile_store.get(job.payload["profile_id"])
    if profile is None:
        raise NotFoundError("profile not found")
    paper = ctx.paper_store.get(job.paper_id)
    if paper is None:
        raise NotFoundError("paper not found")

    # Load markdown if available
    markdown: str | None = None
    md_path = ctx.blob_store.get_markdown_path(job.paper_id)
    if md_path is not None and md_path.exists():
        markdown = md_path.read_text(encoding="utf-8")

    # Render prompt template with paper data
    import json as json_mod  # noqa: PLC0415

    authors_raw = paper.get("authors_json", "[]")
    try:
        authors = json_mod.loads(authors_raw) if authors_raw else []
    except (TypeError, json_mod.JSONDecodeError):
        authors = []

    try:
        rendered = render_prompt_template(
            template=prompt_version["body"],
            paper_id=job.paper_id,
            title=paper.get("title"),
            abstract=paper.get("abstract"),
            authors=authors,
            year=paper.get("year"),
            venue=paper.get("venue"),
            markdown=markdown,
        )
    except NotReadyError as exc:
        return HandlerResult.failed(str(exc), error_code=str(ErrorCode.OUTPUT_PARSE_FAILED))

    # Mark started and call LLM
    started_at = datetime.now(UTC)
    ctx.analysis_store.mark_started(job.run_id)
    llm_profile = _profile_with_api_key(profile)
    logger.info(
        "analyze started for paper %s, model=%s, prompt=%s",
        job.paper_id,
        job.payload["model_name"],
        job.payload["prompt_version_id"],
    )
    response = ctx.llm_client.complete(
        prompt=rendered.text,
        profile=llm_profile,
        model=job.payload["model_name"],
        timeout_s=job.payload.get("timeout_s"),
    )
    cost_usd = _calculate_run_cost(response, llm_profile)

    # Record metrics
    metric_labels = {
        "prompt_version_id": prompt_version["prompt_version_id"],
        "model_name": job.payload["model_name"],
    }
    ctx.metrics.observe("llm_tokens_in", float(response.tokens_in or 0), metric_labels)
    ctx.metrics.observe("llm_tokens_out", float(response.tokens_out or 0), metric_labels)
    if cost_usd is not None:
        ctx.metrics.observe("llm_cost_usd", float(cost_usd), metric_labels)

    cancelled = _check_cancelled(job, ctx)
    if cancelled is not None:
        return cancelled

    # Parse output according to prompt's output_format
    output_format = OutputFormat(prompt_version["output_format"])
    try:
        parsed = parse_llm_output(raw_text=response.text, output_format=output_format)
    except OutputParseFailed as exc:
        _finish_analysis(
            ctx,
            job,
            response,
            prompt_version,
            profile,
            paper,
            markdown=markdown,
            output_json=None,
            validation_issues_json=None,
            error_message=str(exc),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            cost_usd=cost_usd,
        )
        return HandlerResult.failed(str(exc), error_code=str(ErrorCode.OUTPUT_PARSE_FAILED))

    # Flatten and validate extractions (only if structured data was parsed)
    extraction_rows = []
    validation_issues_json: str | None = None
    output_json_data: dict[str, Any] | None = parsed.data

    if parsed.data is not None:
        # Validate against schema if present
        schema = prompt_version.get("extraction_schema_json")
        if isinstance(schema, str):
            schema = json_mod.loads(schema)

        validation = validate_extraction_output(parsed.data, schema)

        # Flatten into extraction rows
        flat = flatten_extractions(parsed.data)
        extraction_rows = flat.rows

        # Collect all issues (validation + flatten warnings)
        all_issues = [
            {
                "path": i.path,
                "severity": i.severity,
                "message": i.message,
                "value_preview": i.value_preview,
            }
            for i in validation.issues
        ] + flat.warnings

        if all_issues:
            validation_issues_json = json_mod.dumps(all_issues)

        if not validation.valid:
            # Store everything we have, then fail
            _finish_analysis(
                ctx,
                job,
                response,
                prompt_version,
                profile,
                paper,
                markdown=markdown,
                output_json=output_json_data,
                validation_issues_json=validation_issues_json,
                error_message="required field validation failed",
                extraction_rows=extraction_rows,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                cost_usd=cost_usd,
            )
            return HandlerResult.failed(
                "required field validation failed",
                error_code=str(ErrorCode.OUTPUT_VALIDATION_FAILED),
            )

    # Store successful analysis
    _finish_analysis(
        ctx,
        job,
        response,
        prompt_version,
        profile,
        paper,
        markdown=markdown,
        output_json=output_json_data,
        validation_issues_json=validation_issues_json,
        error_message=None,
        extraction_rows=extraction_rows,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        cost_usd=cost_usd,
    )
    ctx.paper_store.advance_pipeline_stage_monotonic(job.paper_id, PipelineStage.analyzed)
    return HandlerResult.succeeded()


def _finish_analysis(
    ctx: HandlerContext,
    job: ports.Job,
    response: ports.LLMResponse,
    prompt_version: dict[str, Any],
    profile: dict[str, Any],
    paper: dict[str, Any],
    *,
    markdown: str | None,
    output_json: dict[str, Any] | None,
    validation_issues_json: str | None,
    error_message: str | None,
    started_at: datetime,
    finished_at: datetime,
    cost_usd: float | None,
    extraction_rows: list | None = None,
) -> None:
    """Store artifacts, mark run finished, and upsert extractions."""
    run_id = job.run_id
    paper_id = job.paper_id
    if run_id is None or paper_id is None:
        raise ValueError("analyze finish requires run_id and paper_id")
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    extraction_schema = prompt_version.get("extraction_schema_json")
    if isinstance(extraction_schema, str):
        extraction_schema_hash = hashlib.sha256(extraction_schema.encode("utf-8")).hexdigest()
    elif extraction_schema is None:
        extraction_schema_hash = None
    else:
        extraction_schema_hash = hashlib.sha256(
            json.dumps(extraction_schema, sort_keys=True).encode("utf-8")
        ).hexdigest()

    meta = {
        "run_id": job.run_id,
        "paper_id": job.paper_id,
        "prompt": {
            "prompt_id": prompt_version["prompt_id"],
            "prompt_version_id": prompt_version["prompt_version_id"],
            "version": prompt_version["version"],
            "output_format": prompt_version["output_format"],
            "extraction_schema_hash": extraction_schema_hash,
        },
        "endpoint": {
            "profile_name": profile["name"],
            "base_url": profile["base_url"],
            "model_name": job.payload["model_name"],
            "parameters": {},
            "pricing": {
                "input_price_per_1k_tokens": _as_json_float(
                    profile.get("input_price_per_1k_tokens")
                ),
                "output_price_per_1k_tokens": _as_json_float(
                    profile.get("output_price_per_1k_tokens")
                ),
            },
        },
        "input_provenance": {
            "md_fingerprint_xxh64": paper.get("md_fingerprint_xxh64", "unknown"),
            "pdf_fingerprint_xxh64": paper.get("pdf_fingerprint_xxh64"),
            "md_converter": paper.get("md_converter", "docling"),
            "md_converter_version": paper.get("md_converter_version", ctx.converter.version()),
            "text_slice_strategy": paper.get("text_slice_strategy"),
            "embedding_model": paper.get("embedding_model"),
            "embedding_dimension": paper.get("embedding_dimension"),
        },
        "timing": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": duration_ms,
        },
        "usage": {
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost_usd": cost_usd,
        },
    }
    if validation_issues_json:
        import json as json_mod  # noqa: PLC0415

        meta["validation_issues"] = json_mod.loads(validation_issues_json)

    artifacts = ctx.blob_store.put_analysis_artifacts(
        run_id,
        response.text,
        output_json,
        meta,
    )
    ctx.analysis_store.mark_finished(
        run_id,
        output_md=str(artifacts.get("output_md", "")),
        output_json=str(artifacts.get("output_json")) if output_json else None,
        validation_issues_json=validation_issues_json,
        error_message=error_message,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        cost_usd=cost_usd,
    )

    # Upsert extractions if available
    if extraction_rows and ctx.extraction_store is not None:
        ctx.extraction_store.upsert_extractions(
            run_id=run_id,
            paper_id=paper_id,
            prompt_version_id=prompt_version["prompt_version_id"],
            extractions=extraction_rows,
        )


def handle_discover(job: ports.Job, ctx: HandlerContext) -> HandlerResult:
    if ctx.scholar_client is None or ctx.candidate_store is None:
        return HandlerResult.failed("discover handler dependencies are not configured")

    query = str(job.payload.get("query", "")).strip()
    if not query:
        return HandlerResult.failed("discover query is required")

    filters = job.payload.get("filters", {})
    if not isinstance(filters, dict):
        return HandlerResult.failed("discover filters must be a dict")

    max_results = int(job.payload.get("max_results", 50))
    page_size = int(job.payload.get("page_size", min(max_results, 100)))

    logger.info("discover started, query=%r, max_results=%d", query, max_results)
    results = ctx.scholar_client.search(
        query=query,
        filters=filters,
        max_results=max_results,
        page_size=page_size,
    )
    stored_count = 0
    for result in results:
        source_paper_id = str(result.get("source_paper_id", "")).strip()
        if not source_paper_id:
            continue
        if (
            ctx.candidate_store.get_candidate_by_source("semantic_scholar", source_paper_id)
            is not None
        ):
            continue
        ctx.candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": source_paper_id,
                "title": result.get("title") or "",
                "year": result.get("year"),
                "venue": result.get("venue"),
                "authors_json": json.dumps(result.get("authors", [])),
                "abstract": result.get("abstract"),
                "external_ids_json": (
                    json.dumps(result.get("external_ids"))
                    if result.get("external_ids") is not None
                    else None
                ),
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )
        stored_count += 1
    logger.info("discover completed, query=%r, stored=%d", query, stored_count)
    return HandlerResult.succeeded()


HANDLERS: dict[str, Any] = {
    "discover": handle_discover,
    "download": handle_download,
    "convert": handle_convert,
    "embed": handle_embed,
    "analyze": handle_analyze,
}
