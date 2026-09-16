from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nsqd.composition import NsqdContainer
from nsqd.infra.paper_runtime import markdown_reader
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.project_runtime import run_project
from papers.app import use_cases
from papers.app.composition_root import AppContainer
from papers.config.settings import Settings
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import (
    PiccoloCandidateImporter,
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloPaperExternalIdStore,
    PiccoloPaperProjectStore,
)
from papers.ui.path_policy import resolve_ui_input
from papers.ui.workflow_services import WorkflowCallback


def build_paper_service_values(base: AppContainer, settings: Settings) -> dict[str, Any]:
    candidate_store = PiccoloCandidateStore()
    extraction_store = PiccoloExtractionStore()
    external_id_store = PiccoloPaperExternalIdStore()
    return {
        "discover": use_cases.DiscoverCandidatesUseCase(
            scholar_client=base.scholar_client,
            candidate_store=candidate_store,
        ),
        "import_candidate": use_cases.ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=base.paper_store,
            job_queue=base.job_queue,
            external_id_store=external_id_store,
            atomic_importer=PiccoloCandidateImporter(),
            project_store=base.project_store,
            tag_store=base.tag_store,
            atomic_candidate_import=base.atomic_candidate_import,
        ),
        "reject_candidate": use_cases.RejectCandidateUseCase(candidate_store=candidate_store),
        "search": use_cases.SearchPapersUseCase(
            papers_fts=PiccoloPaperFTS(),
            vector_index=base.vector_index,
            embedder=base.embedder,
        ),
        "filter_extractions": use_cases.FilterByExtractionsUseCase(
            extraction_store=extraction_store
        ),
        "aggregate_extractions": use_cases.AggregateExtractionsUseCase(
            extraction_store=extraction_store
        ),
        "get_candidate": candidate_store.get_candidate,
        "list_paper": base.paper_store.get,
        "list_runs": base.analysis_store.list_runs,
        "list_jobs": lambda status, limit: base.job_queue.list_jobs(status=status, limit=limit),
        "run_next_job": lambda: base.job_runner.run_next(datetime.now(UTC)),
        "enqueue_job": lambda job_type, paper_id, run_id, payload: base.job_queue.enqueue(
            job_type, paper_id, run_id, payload
        ),
        "cancel_job": base.job_queue.cancel,
        "delete_job": base.job_queue.delete_job,
        "bulk_delete_jobs": base.job_queue.bulk_delete_jobs,
        "bulk_cancel_jobs": base.job_queue.bulk_cancel_jobs,
        "get_paper_markdown": markdown_reader(base.blob_store),
        "list_extractions": extraction_store.list_by_paper,
        "delete_paper": base.paper_store.delete_paper,
        "reset_pipeline_stage": base.paper_store.reset_pipeline_stage,
        "synthesize_from_corpus": use_cases.SynthesizeFromCorpusUseCase(
            embedder=base.embedder,
            vector_index=base.vector_index,
            paper_store=base.paper_store,
            blob_store=base.blob_store,
            llm_client=base.llm_client,
            paper_project_store=PiccoloPaperProjectStore(),
        ),
        "ui_settings": {
            "search_max_results": settings.ui.search_max_results,
            "scholar_api_key_set": bool(settings.scholar.api_key),
            "scholar_rate_limit": settings.scholar.rate_limit_per_second,
            "require_open_access": settings.scholar.require_open_access,
        },
    }


def build_projection_callbacks(
    nsqd: NsqdContainer,
    *,
    repo_root: Path,
    db_path: Path,
    index_path: Path,
) -> tuple[WorkflowCallback, WorkflowCallback]:
    def project_records(*, projection_path: str, manifest_path: str) -> dict[str, Any]:
        embedder = nsqd.ctx.embedder
        if embedder is None:
            raise ValueError("embedder is not configured")
        projection = resolve_ui_input(projection_path, repo_root=repo_root, field="projection_path")
        manifest = resolve_ui_input(manifest_path, repo_root=repo_root, field="manifest_path")
        return run_project(
            projection_path=projection,
            manifest_path=manifest,
            db_path=db_path,
            index_path=index_path,
            embedder=embedder,
        )

    def approve_digest(*, digest: str) -> dict[str, Any]:
        token = digest.strip().lower()
        if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
            raise ValueError("digest must be a SHA-256 hex digest")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        database = PiccoloDatabase(db_path)
        database.initialize_schema()
        digest_store = PiccoloApprovedDigestStore(database)
        digest_store.add(token, approved_at=datetime.now(UTC))
        if token not in digest_store.list_digests():
            raise ValueError("approved digest was not persisted")
        return {"digest": token, "approved": True}

    return project_records, approve_digest
