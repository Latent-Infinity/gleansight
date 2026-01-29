from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Job(Protocol):
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime | None


@runtime_checkable
class JobQueue(Protocol):
    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str: ...

    def claim_next(self, now: datetime) -> Job | None: ...

    def mark_succeeded(self, job_id: str, metrics: dict[str, Any] | None = None) -> None: ...

    def mark_retryable(
        self,
        job_id: str,
        error: str,
        run_after: datetime,
        metrics: dict[str, Any] | None = None,
    ) -> None: ...

    def mark_failed(
        self,
        job_id: str,
        error: str,
        metrics: dict[str, Any] | None = None,
    ) -> None: ...

    def cancel(self, job_id: str) -> None: ...

    def is_cancelled(self, job_id: str) -> bool: ...


@runtime_checkable
class PaperStore(Protocol):
    def create_paper(self, fields: dict[str, Any]) -> str: ...

    def get(self, paper_id: str) -> dict[str, Any] | None: ...

    def update_metadata(self, paper_id: str, fields: dict[str, Any]) -> None: ...

    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None: ...

    def set_markdown_provenance(
        self,
        paper_id: str,
        md_xxh64: str,
        src_pdf_xxh64: str,
        converter: str,
        converter_version: str,
    ) -> None: ...

    def set_embedding_state(
        self,
        paper_id: str,
        embedding_model: str,
        embedding_dimension: int,
        text_slice_strategy: str,
        embedded_from_md_xxh64: str,
    ) -> None: ...

    def advance_pipeline_stage_monotonic(self, paper_id: str, new_stage: str) -> None: ...

    def set_pipeline_health_error(
        self,
        paper_id: str,
        error_code: str,
        message: str,
        job_id: str | None,
    ) -> None: ...

    def clear_pipeline_health_if_recovered(self, paper_id: str, job_type: str) -> None: ...


@runtime_checkable
class Extraction(Protocol):
    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: float | None
    value_boolean: int | None


@runtime_checkable
class ExtractionStore(Protocol):
    def upsert_extractions(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        extractions: list[Extraction],
    ) -> None: ...

    def list_by_paper(
        self,
        paper_id: str,
        prompt_version_id: str | None = None,
        successful_only: bool = True,
    ) -> list[Extraction]: ...

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict[str, Any],
    ) -> list[str]: ...


@runtime_checkable
class BlobStore(Protocol):
    def put_pdf(self, src_path: Path) -> tuple[str, Path]: ...

    def get_pdf_path(self, pdf_xxh64: str) -> Path | None: ...

    def put_markdown(self, paper_id: str, markdown: str) -> tuple[Path, str]: ...

    def get_markdown_path(self, paper_id: str) -> Path | None: ...

    def put_analysis_artifacts(
        self,
        run_id: str,
        output_md: str,
        output_json: dict | None,
        meta_json: dict,
    ) -> dict[str, Path]: ...


@runtime_checkable
class VectorIndex(Protocol):
    def upsert(self, paper_id: str, embedding: list[float]) -> None: ...

    def query(self, embedding: list[float], limit: int) -> list[tuple[str, float]]: ...


@dataclass(frozen=True)
class ConverterResult:
    ok: bool
    markdown: str | None
    error_code: str | None
    error_message: str | None


@runtime_checkable
class Converter(Protocol):
    def pdf_to_markdown(self, pdf_path: Path) -> ConverterResult: ...

    def version(self) -> str: ...


@runtime_checkable
class Embedder(Protocol):
    def model_name(self) -> str: ...

    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse: ...


@runtime_checkable
class ScholarClient(Protocol):
    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class PromptStore(Protocol):
    def create_prompt(self, prompt_id: str, name: str, created_at: str | None = None) -> None: ...

    def create_version(
        self,
        prompt_version_id: str,
        prompt_id: str,
        version: int,
        body: str,
        output_format: str,
        extraction_schema_json: dict[str, Any] | None = None,
    ) -> None: ...

    def get_latest_version(self, prompt_id: str) -> dict[str, Any] | None: ...

    def get_version(self, prompt_version_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class ProfileStore(Protocol):
    def create_profile(self, profile_id: str, name: str, base_url: str) -> None: ...

    def get(self, profile_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class AnalysisRunStore(Protocol):
    def create_run(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> None: ...

    def mark_started(self, run_id: str) -> None: ...

    def mark_finished(
        self,
        run_id: str,
        *,
        output_md: str | None = None,
        output_json: str | None = None,
        validation_issues_json: str | None = None,
        error_message: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
    ) -> None: ...

    def get_latest_successful_run(
        self,
        *,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> dict[str, Any] | None: ...
