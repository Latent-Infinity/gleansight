from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nsqd.app.use_cases import MapSnapshotUseCase
from nsqd.infra.paper_runtime import compose_default_runtime, markdown_reader
from papers.app import use_cases
from papers.app.composition_root import build_container
from papers.config.settings import (
    DEFAULT_OLLAMA_BASE_URL,
    ConfigurationError,
    load_settings,
    packaged_defaults_path,
    public_configuration_error_message,
)
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import (
    PiccoloCandidateImporter,
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloPaperExternalIdStore,
    PiccoloPaperProjectStore,
)
from papers.ui.app import UIServices, run_app


def build_ui_services(
    config_path: Path | None = None,
    llm_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: str | None = None,
) -> UIServices:
    """Build UIServices container with all dependencies wired."""
    settings = load_settings(defaults_path=packaged_defaults_path(), override_path=config_path)
    base = build_container(
        settings,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
    )

    runtime = compose_default_runtime(
        papers=base,
        nsqd_db_path=Path(settings.data.root) / "nsqd" / "nsqd.sqlite",
        nsqd_index_path=Path(settings.data.root) / "nsqd" / "corpus.lancedb",
        llm_base_url=llm_base_url,
    )
    nsqd = runtime.nsqd
    candidate_store = PiccoloCandidateStore()
    extraction_store = PiccoloExtractionStore()
    external_id_store = PiccoloPaperExternalIdStore()
    papers_fts = PiccoloPaperFTS()

    return UIServices(
        discover=use_cases.DiscoverCandidatesUseCase(
            scholar_client=base.scholar_client,
            candidate_store=candidate_store,
        ),
        import_candidate=use_cases.ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=base.paper_store,
            job_queue=base.job_queue,
            external_id_store=external_id_store,
            atomic_importer=PiccoloCandidateImporter(),
            project_store=base.project_store,
            tag_store=base.tag_store,
            atomic_candidate_import=base.atomic_candidate_import,
        ),
        reject_candidate=use_cases.RejectCandidateUseCase(
            candidate_store=candidate_store,
        ),
        search=use_cases.SearchPapersUseCase(
            papers_fts=papers_fts,
            vector_index=base.vector_index,
            embedder=base.embedder,
        ),
        filter_extractions=use_cases.FilterByExtractionsUseCase(extraction_store=extraction_store),
        aggregate_extractions=use_cases.AggregateExtractionsUseCase(
            extraction_store=extraction_store
        ),
        get_candidate=candidate_store.get_candidate,
        list_paper=base.paper_store.get,
        list_runs=base.analysis_store.list_runs,
        list_jobs=lambda status, limit: base.job_queue.list_jobs(status=status, limit=limit),
        run_next_job=lambda: base.job_runner.run_next(datetime.now(UTC)),
        enqueue_job=lambda job_type, paper_id, run_id, payload: base.job_queue.enqueue(
            job_type, paper_id, run_id, payload
        ),
        cancel_job=base.job_queue.cancel,
        delete_job=base.job_queue.delete_job,
        bulk_delete_jobs=base.job_queue.bulk_delete_jobs,
        bulk_cancel_jobs=base.job_queue.bulk_cancel_jobs,
        get_paper_markdown=markdown_reader(base.blob_store),
        list_extractions=extraction_store.list_by_paper,
        delete_paper=base.paper_store.delete_paper,
        reset_pipeline_stage=base.paper_store.reset_pipeline_stage,
        synthesize_from_corpus=use_cases.SynthesizeFromCorpusUseCase(
            embedder=base.embedder,
            vector_index=base.vector_index,
            paper_store=base.paper_store,
            blob_store=base.blob_store,
            llm_client=base.llm_client,
            paper_project_store=PiccoloPaperProjectStore(),
        ),
        ui_settings={
            "search_max_results": settings.ui.search_max_results,
            "scholar_api_key_set": bool(settings.scholar.api_key),
            "scholar_rate_limit": settings.scholar.rate_limit_per_second,
            "require_open_access": settings.scholar.require_open_access,
        },
        map_snapshot=lambda **kwargs: MapSnapshotUseCase(
            snapshots=nsqd.ctx.snapshots,
            records=nsqd.ctx.records,
            morph=nsqd.ctx.morph,
            clock=nsqd.clock,
        ).run(**kwargs),
        list_archive_elites=nsqd.ctx.cards.list_elites,
        get_frontier_card=nsqd.ctx.cards.get_card,
    )


def main(
    config: str | None = None,
    llm_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: str | None = None,
) -> None:
    """Launch the Gleansight UI application."""
    config_path = Path(config) if config else None
    try:
        services = build_ui_services(
            config_path=config_path,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
        )
    except ConfigurationError as exc:
        raise SystemExit(public_configuration_error_message(exc)) from None
    run_app(services)


if __name__ == "__main__":
    main()
