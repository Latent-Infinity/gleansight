from __future__ import annotations

from datetime import datetime
from pathlib import Path

from papers.app import ports


class FakeJob:
    job_id = "job"
    type = "download"
    status = "queued"
    paper_id = "paper"
    run_id = None
    payload: dict[str, object] = {}
    attempts = 0
    max_attempts = 3
    run_after = None


class FakeJobQueue:
    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict,
        run_after=None,
    ) -> str:
        return "job"

    def claim_next(self, now: datetime):
        return None

    def mark_succeeded(self, job_id: str, metrics=None) -> None:  # noqa: ANN001 - test stub
        return None

    def mark_retryable(self, job_id: str, error: str, run_after: datetime, metrics=None) -> None:  # noqa: ANN001
        return None

    def mark_failed(self, job_id: str, error: str, metrics=None) -> None:  # noqa: ANN001
        return None

    def cancel(self, job_id: str) -> None:
        return None

    def is_cancelled(self, job_id: str) -> bool:
        return False

    def requeue_running_before(self, cutoff: datetime, error: str) -> list[str]:
        return []

    def delete_job(self, job_id: str) -> None:
        return None

    def bulk_delete_jobs(self, job_ids: list[str]) -> int:
        return len(job_ids)

    def bulk_cancel_jobs(self, job_ids: list[str]) -> int:
        return len(job_ids)


class FakePaperStore:
    def create_paper(self, fields: dict) -> str:
        return "paper"

    def get(self, paper_id: str):
        return None

    def update_metadata(self, paper_id: str, fields: dict) -> None:
        return None

    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None:
        return None

    def set_markdown_provenance(
        self,
        paper_id: str,
        md_xxh64: str,
        src_pdf_xxh64: str,
        converter: str,
        converter_version: str,
    ) -> None:
        return None

    def set_embedding_state(
        self,
        paper_id: str,
        embedding_model: str,
        embedding_dimension: int,
        text_slice_strategy: str,
        embedded_from_md_xxh64: str,
    ) -> None:
        return None

    def advance_pipeline_stage_monotonic(self, paper_id: str, new_stage: str) -> None:
        return None

    def set_pipeline_health_error(
        self,
        paper_id: str,
        error_code: str,
        message: str,
        job_id: str | None,
    ) -> None:
        return None

    def clear_pipeline_health_if_recovered(self, paper_id: str, job_type: str) -> None:
        return None

    def list_papers_with_markdown(self) -> list[str]:
        return []

    def delete_paper(self, paper_id: str) -> None:
        return None

    def reset_pipeline_stage(self, paper_id: str, stage: str) -> None:
        return None


class FakeExtraction:
    entity_type = "paper"
    entity_ref = None
    field_path = "field"
    value_text = "value"
    value_numeric = None
    value_boolean = None


class FakeExtractionStore:
    def upsert_extractions(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        extractions: list,
    ) -> None:
        return None

    def list_by_paper(
        self,
        paper_id: str,
        prompt_version_id: str | None = None,
        successful_only: bool = True,
    ):
        return []

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict,
        latest_only: bool = True,
    ):
        return []

    def count_by_value(self, field_path: str, prompt_version_id: str, latest_only: bool = True):
        return {}

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ):
        return None

    def search_text(
        self,
        query: str,
        *,
        prompt_version_id: str,
        field_path: str | None = None,
        entity_type: str | None = None,
        entity_ref: str | None = None,
        limit: int = 50,
    ):
        return []


class FakeBlobStore:
    def put_pdf(self, src_path: Path):
        return "xxh64", Path("/tmp/x.pdf")

    def get_pdf_path(self, pdf_xxh64: str):
        return None

    def put_markdown(self, paper_id: str, markdown: str):
        return Path("/tmp/x.md"), "md_xxh64"

    def get_markdown_path(self, paper_id: str):
        return None

    def put_analysis_artifacts(
        self,
        run_id: str,
        output_md: str,
        output_json: dict | None,
        meta_json: dict,
    ):
        return {"output": Path("/tmp/out.md")}


class FakeVectorIndex:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []

    def reset(self) -> None:
        return None


class FakeConverter:
    def pdf_to_markdown(self, pdf_path: Path):
        return ports.ConverterResult(ok=True, markdown="", error_code=None, error_message=None)

    def version(self) -> str:
        return "1.0"


class FakeEmbedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 384

    def embed(self, text: str):
        return [0.0]


class FakeLLMClient:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        return ports.LLMResponse(text="", tokens_in=None, tokens_out=None, cost_usd=None)


class FakeScholarClient:
    def search(self, query: str, filters: dict, max_results: int, page_size: int):
        return []


class FakePromptStore:
    def create_prompt(
        self,
        prompt_id: str,
        name: str,
        description: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        return None

    def get_prompt(self, prompt_id: str):
        return None

    def create_version(
        self,
        prompt_version_id: str,
        prompt_id: str,
        version: int,
        body: str,
        output_format: str,
        extraction_schema_json: dict | None = None,
    ) -> None:
        return None

    def get_latest_version(self, prompt_id: str):
        return None

    def get_version(self, prompt_version_id: str):
        return None


class FakeProfileStore:
    def create_profile(self, profile_id: str, name: str, base_url: str) -> None:
        return None

    def update_profile(self, profile_id: str, name: str, base_url: str) -> None:
        return None

    def get(self, profile_id: str):
        return None


class FakeAnalysisRunStore:
    def create_run(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> None:
        return None

    def mark_started(self, run_id: str) -> None:
        return None

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
        return None

    def get_latest_successful_run(
        self,
        *,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ):
        return None

    def list_runs(self, paper_id: str) -> list[dict]:
        return []


class FakeTagStore:
    def create_tag(self, tag_id: str, name: str, tag_type: str, created_at: str | None = None):
        return None

    def get(self, tag_id: str):
        return None

    def get_by_name(self, name: str):
        return None


class FakePaperTagStore:
    def is_attached(self, paper_id: str, tag_id: str) -> bool:
        return False

    def attach(self, paper_id: str, tag_id: str, confidence: float | None = None) -> None:
        return None


class FakeProjectStore:
    def create_project(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> None:
        return None

    def get(self, project_id: str):
        return None

    def get_by_name(self, name: str):
        return None


class FakePaperProjectStore:
    def is_attached(self, paper_id: str, project_id: str) -> bool:
        return False

    def attach(self, paper_id: str, project_id: str, label: str | None = None) -> None:
        return None

    def list_paper_ids(self, project_id: str, label: str | None = None) -> list[str]:
        return []


def test_protocols_are_runtime_checkable():
    assert isinstance(FakeJob(), ports.Job)
    assert isinstance(FakeJobQueue(), ports.JobQueue)
    assert isinstance(FakePaperStore(), ports.PaperStore)
    assert isinstance(FakeExtraction(), ports.Extraction)
    assert isinstance(FakeExtractionStore(), ports.ExtractionStore)
    assert isinstance(FakeBlobStore(), ports.BlobStore)
    assert isinstance(FakeVectorIndex(), ports.VectorIndex)
    assert isinstance(FakeConverter(), ports.Converter)
    assert isinstance(FakeEmbedder(), ports.Embedder)
    assert isinstance(FakeLLMClient(), ports.LLMClient)
    assert isinstance(FakeScholarClient(), ports.ScholarClient)
    assert isinstance(FakePromptStore(), ports.PromptStore)
    assert isinstance(FakeProfileStore(), ports.ProfileStore)
    assert isinstance(FakeAnalysisRunStore(), ports.AnalysisRunStore)
    assert isinstance(FakeTagStore(), ports.TagStore)
    assert isinstance(FakePaperTagStore(), ports.PaperTagStore)
    assert isinstance(FakeProjectStore(), ports.ProjectStore)
    assert isinstance(FakePaperProjectStore(), ports.PaperProjectStore)
