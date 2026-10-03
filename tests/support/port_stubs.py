from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from papers.app.ports import (
    AnalysisRunStore,
    BlobStore,
    CandidateStore,
    Embedder,
    Extraction,
    ExtractionStore,
    Job,
    JobQueue,
    PaperProjectStore,
    PaperStore,
    ProfileStore,
    ProjectStore,
    PromptStore,
    ScholarClient,
    TagStore,
    VectorIndex,
)


def _unexpected(method: str) -> None:
    raise NotImplementedError(f"unexpected {method} call")


class CandidateStoreStub(CandidateStore):
    def create_candidate(self, fields: dict[str, Any]) -> str:
        _unexpected("create_candidate")
        raise AssertionError

    def get_candidate_by_source(self, source: str, source_paper_id: str) -> dict[str, Any] | None:
        _unexpected("get_candidate_by_source")
        raise AssertionError

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        _unexpected("get_candidate")
        raise AssertionError

    def mark_imported(self, candidate_id: str, paper_id: str) -> None:
        _unexpected("mark_imported")

    def mark_rejected(self, candidate_id: str) -> None:
        _unexpected("mark_rejected")


class ScholarClientStub(ScholarClient):
    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        _unexpected("search")
        raise AssertionError


class JobQueueStub(JobQueue):
    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        _unexpected("job enqueue")
        raise AssertionError

    def claim_next(self, now: datetime) -> Job | None:
        _unexpected("job claim")
        raise AssertionError

    def mark_succeeded(self, job_id: str, metrics: dict[str, Any] | None = None) -> None:
        _unexpected("job success")

    def mark_retryable(
        self,
        job_id: str,
        error: str,
        run_after: datetime,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        _unexpected("job retry")

    def mark_failed(self, job_id: str, error: str, metrics: dict[str, Any] | None = None) -> None:
        _unexpected("job failure")

    def cancel(self, job_id: str) -> None:
        _unexpected("job cancel")

    def is_cancelled(self, job_id: str) -> bool:
        _unexpected("job cancellation check")
        raise AssertionError

    def requeue_running_before(self, cutoff: datetime, error: str) -> list[str]:
        _unexpected("job recovery")
        raise AssertionError

    def delete_job(self, job_id: str) -> None:
        _unexpected("job deletion")

    def bulk_delete_jobs(self, job_ids: list[str]) -> int:
        _unexpected("bulk job deletion")
        raise AssertionError

    def bulk_cancel_jobs(self, job_ids: list[str]) -> int:
        _unexpected("bulk job cancellation")
        raise AssertionError


class PaperStoreStub(PaperStore):
    def create_paper(self, fields: dict[str, Any]) -> str:
        _unexpected("paper creation")
        raise AssertionError

    def get(self, paper_id: str) -> dict[str, Any] | None:
        _unexpected("paper lookup")
        raise AssertionError

    def update_metadata(self, paper_id: str, fields: dict[str, Any]) -> None:
        _unexpected("paper metadata update")

    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None:
        _unexpected("paper PDF fingerprint")

    def set_markdown_provenance(
        self,
        paper_id: str,
        md_xxh64: str,
        src_pdf_xxh64: str,
        converter: str,
        converter_version: str,
    ) -> None:
        _unexpected("paper markdown provenance")

    def set_embedding_state(
        self,
        paper_id: str,
        embedding_model: str,
        embedding_dimension: int,
        text_slice_strategy: str,
        embedded_from_md_xxh64: str,
    ) -> None:
        _unexpected("paper embedding state")

    def advance_pipeline_stage_monotonic(self, paper_id: str, new_stage: str) -> None:
        _unexpected("paper pipeline stage")

    def set_pipeline_health_error(
        self, paper_id: str, error_code: str, message: str, job_id: str | None
    ) -> None:
        _unexpected("paper health error")

    def clear_pipeline_health_if_recovered(self, paper_id: str, job_type: str) -> None:
        _unexpected("paper health recovery")

    def list_papers_with_markdown(self) -> list[str]:
        _unexpected("paper markdown listing")
        raise AssertionError

    def delete_paper(self, paper_id: str) -> None:
        _unexpected("paper deletion")

    def reset_pipeline_stage(self, paper_id: str, stage: str) -> None:
        _unexpected("paper pipeline reset")


class BlobStoreStub(BlobStore):
    def put_pdf(self, src_path: Path) -> tuple[str, Path]:
        _unexpected("PDF storage")
        raise AssertionError

    def get_pdf_path(self, pdf_xxh64: str) -> Path | None:
        _unexpected("PDF lookup")
        raise AssertionError

    def put_markdown(self, paper_id: str, markdown: str) -> tuple[Path, str]:
        _unexpected("markdown storage")
        raise AssertionError

    def get_markdown_path(self, paper_id: str) -> Path | None:
        _unexpected("markdown lookup")
        raise AssertionError

    def put_analysis_artifacts(
        self, run_id: str, output_md: str, output_json: dict | None, meta_json: dict
    ) -> dict[str, Path]:
        _unexpected("analysis artifact storage")
        raise AssertionError


class EmbedderStub(Embedder):
    def model_name(self) -> str:
        _unexpected("embedding model name")
        raise AssertionError

    def dimension(self) -> int:
        _unexpected("embedding dimension")
        raise AssertionError

    def embed(self, text: str) -> list[float]:
        _unexpected("embedding")
        raise AssertionError


class PromptStoreStub(PromptStore):
    def create_prompt(
        self,
        prompt_id: str,
        name: str,
        description: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        _unexpected("prompt creation")

    def get_prompt(self, prompt_id: str) -> dict[str, Any] | None:
        _unexpected("prompt lookup")
        raise AssertionError

    def create_version(
        self,
        prompt_version_id: str,
        prompt_id: str,
        version: int,
        body: str,
        output_format: str,
        extraction_schema_json: dict[str, Any] | None = None,
    ) -> None:
        _unexpected("prompt version creation")

    def get_latest_version(self, prompt_id: str) -> dict[str, Any] | None:
        _unexpected("latest prompt version lookup")
        raise AssertionError

    def get_version(self, prompt_version_id: str) -> dict[str, Any] | None:
        _unexpected("prompt version lookup")
        raise AssertionError


class ProfileStoreStub(ProfileStore):
    def create_profile(self, profile_id: str, name: str, base_url: str) -> None:
        _unexpected("profile creation")

    def update_profile(self, profile_id: str, name: str, base_url: str) -> None:
        _unexpected("profile update")

    def get(self, profile_id: str) -> dict[str, Any] | None:
        _unexpected("profile lookup")
        raise AssertionError


class AnalysisRunStoreStub(AnalysisRunStore):
    def create_run(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> None:
        _unexpected("analysis run creation")

    def mark_started(self, run_id: str) -> None:
        _unexpected("analysis run start")

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
    ) -> None:
        _unexpected("analysis run finish")

    def get_latest_successful_run(
        self,
        *,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> dict[str, Any] | None:
        _unexpected("latest analysis lookup")
        raise AssertionError

    def list_runs(self, paper_id: str) -> list[dict[str, Any]]:
        _unexpected("analysis run listing")
        raise AssertionError


class PaperProjectStoreStub(PaperProjectStore):
    def is_attached(self, paper_id: str, project_id: str) -> bool:
        _unexpected("paper project attachment check")
        raise AssertionError

    def attach(self, paper_id: str, project_id: str, label: str | None = None) -> None:
        _unexpected("paper project attachment")

    def list_paper_ids(self, project_id: str, label: str | None = None) -> list[str]:
        _unexpected("project paper listing")
        raise AssertionError


class ProjectStoreStub(ProjectStore):
    def create_project(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> None:
        _unexpected("project creation")

    def get(self, project_id: str) -> dict[str, Any] | None:
        _unexpected("project lookup")
        raise AssertionError

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        _unexpected("project name lookup")
        raise AssertionError


class TagStoreStub(TagStore):
    def create_tag(
        self, tag_id: str, name: str, tag_type: str, created_at: str | None = None
    ) -> None:
        _unexpected("tag creation")

    def get(self, tag_id: str) -> dict[str, Any] | None:
        _unexpected("tag lookup")
        raise AssertionError

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        _unexpected("tag name lookup")
        raise AssertionError


class ExtractionStoreStub(ExtractionStore):
    def upsert_extractions(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        extractions: list[Extraction],
    ) -> None:
        _unexpected("extraction upsert")

    def list_by_paper(
        self,
        paper_id: str,
        prompt_version_id: str | None = None,
        successful_only: bool = True,
    ) -> list[Extraction]:
        _unexpected("paper extraction listing")
        raise AssertionError

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict[str, Any],
        latest_only: bool = True,
    ) -> list[str]:
        _unexpected("extraction query")
        raise AssertionError

    def count_by_value(
        self, field_path: str, prompt_version_id: str, latest_only: bool = True
    ) -> dict[str, int]:
        _unexpected("extraction value count")
        raise AssertionError

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ) -> float | dict[str, float] | None:
        _unexpected("extraction numeric average")
        raise AssertionError

    def search_text(
        self,
        query: str,
        *,
        prompt_version_id: str,
        field_path: str | None = None,
        entity_type: str | None = None,
        entity_ref: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        _unexpected("extraction text search")
        raise AssertionError


class VectorIndexStub(VectorIndex):
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        raise NotImplementedError("unexpected vector upsert")

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        raise NotImplementedError("unexpected vector query")

    def reset(self) -> None:
        raise NotImplementedError("unexpected vector reset")
