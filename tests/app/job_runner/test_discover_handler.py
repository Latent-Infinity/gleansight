from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from papers.app.job_runner.handlers import HandlerContext, handle_discover


class _PaperStore:
    def create_paper(self, fields: dict):
        return ""

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


class _JobQueue:
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

    def mark_succeeded(self, job_id: str, metrics=None) -> None:  # noqa: ANN001
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


class _BlobStore:
    def put_pdf(self, src_path: Path):
        return "xxh64", src_path

    def get_pdf_path(self, pdf_xxh64: str):
        return None

    def put_markdown(self, paper_id: str, markdown: str):
        return Path("/tmp/x.md"), "md"

    def get_markdown_path(self, paper_id: str):
        return None

    def put_analysis_artifacts(
        self, run_id: str, output_md: str, output_json: dict | None, meta_json: dict
    ):
        return {}


class _Converter:
    def pdf_to_markdown(self, pdf_path: Path):
        raise AssertionError("not used")

    def version(self) -> str:
        return "1.0"


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 1

    def embed(self, text: str) -> list[float]:
        return [0.0]


class _Vector:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        raise AssertionError("not used")


class _PromptStore:
    def get_version(self, prompt_version_id: str):
        return None


class _ProfileStore:
    def get(self, profile_id: str):
        return None


class _AnalysisStore:
    def create_run(
        self, run_id: str, paper_id: str, prompt_version_id: str, profile_id: str, model_name: str
    ) -> None:
        return None

    def mark_started(self, run_id: str) -> None:
        return None

    def mark_finished(self, run_id: str, **kwargs) -> None:  # noqa: ANN003
        return None

    def get_latest_successful_run(self, **kwargs):  # noqa: ANN003
        return None


class _Scholar:
    def search(self, query: str, filters: dict, max_results: int, page_size: int):
        return [
            {
                "source_paper_id": "s2-1",
                "title": "One",
                "authors": ["A"],
                "abstract": "x",
                "external_ids": {"DOI": "10.1/abc"},
            },
            {
                "source_paper_id": "s2-2",
                "title": "Two",
                "authors": ["B"],
                "abstract": "y",
                "external_ids": {"ArXiv": "1234.5678"},
            },
        ]


class _CandidateStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def create_candidate(self, fields: dict) -> str:
        key = (fields["source"], fields["source_paper_id"])
        self.rows[key] = fields
        return fields["candidate_id"]

    def get_candidate_by_source(self, source: str, source_paper_id: str):
        return self.rows.get((source, source_paper_id))


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


def _ctx(candidate_store: _CandidateStore, scholar: _Scholar) -> HandlerContext:
    return HandlerContext(
        paper_store=_PaperStore(),
        job_queue=_JobQueue(),
        blob_store=_BlobStore(),
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_Vector(),
        llm_client=_LLM(),
        prompt_store=_PromptStore(),
        profile_store=_ProfileStore(),
        analysis_store=_AnalysisStore(),
        scholar_client=scholar,
        candidate_store=candidate_store,
    )


def test_handle_discover_creates_candidates() -> None:
    store = _CandidateStore()
    result = handle_discover(
        _Job(
            job_id="j1",
            type="discover",
            status="queued",
            paper_id=None,
            run_id=None,
            payload={"query": "transformers", "filters": {}, "max_results": 2, "page_size": 2},
            attempts=0,
            max_attempts=3,
            run_after=None,
        ),
        _ctx(store, _Scholar()),
    )
    assert result.status == "succeeded"
    assert len(store.rows) == 2


def test_handle_discover_requires_non_empty_query() -> None:
    store = _CandidateStore()
    result = handle_discover(
        _Job(
            job_id="j1",
            type="discover",
            status="queued",
            paper_id=None,
            run_id=None,
            payload={"query": "   "},
            attempts=0,
            max_attempts=3,
            run_after=None,
        ),
        _ctx(store, _Scholar()),
    )
    assert result.status == "failed"
    assert result.error == "discover query is required"
