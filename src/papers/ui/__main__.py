from __future__ import annotations

from pathlib import Path

from papers.app import use_cases
from papers.app.composition_root import build_container
from papers.config.settings import load_settings
from papers.infra.piccolo.stores import (
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloPaperExternalIdStore,
)
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.ui.app import UIServices, run_app


def build_ui_services(
    config_path: Path | None = None,
    llm_base_url: str = "http://localhost:8000",
    llm_api_key: str | None = None,
) -> UIServices:
    """Build UIServices container with all dependencies wired."""
    defaults_path = Path(__file__).resolve().parents[1] / "config" / "defaults.toml"
    settings = load_settings(defaults_path=defaults_path, override_path=config_path)
    base = build_container(
        settings,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
    )

    candidate_store = PiccoloCandidateStore()
    extraction_store = PiccoloExtractionStore()
    external_id_store = PiccoloPaperExternalIdStore()
    papers_fts = PiccoloPaperFTS()

    def get_paper_markdown(paper_id: str) -> str | None:
        """Get the markdown content for a paper, if available."""
        md_path = base.blob_store.get_markdown_path(paper_id)
        if md_path is None or not md_path.exists():
            return None
        try:
            return md_path.read_text(encoding="utf-8")
        except OSError:
            return None

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
        ),
        reject_candidate=use_cases.RejectCandidateUseCase(
            candidate_store=candidate_store,
        ),
        search=use_cases.SearchPapersUseCase(
            papers_fts=papers_fts,
            vector_index=base.vector_index,
            embedder=base.embedder,
        ),
        filter_extractions=use_cases.FilterByExtractionsUseCase(
            extraction_store=extraction_store
        ),
        aggregate_extractions=use_cases.AggregateExtractionsUseCase(
            extraction_store=extraction_store
        ),
        get_candidate=candidate_store.get_candidate,
        list_paper=base.paper_store.get,
        list_runs=base.analysis_store.list_runs,
        list_jobs=base.job_queue.list_jobs,
        get_paper_markdown=get_paper_markdown,
        ui_settings={
            "search_max_results": settings.ui.search_max_results,
            "scholar_api_key_set": bool(settings.scholar.api_key),
            "scholar_rate_limit": settings.scholar.rate_limit_per_second,
            "require_open_access": settings.scholar.require_open_access,
        },
    )


def main(
    config: str | None = None,
    llm_base_url: str = "http://localhost:8000",
    llm_api_key: str | None = None,
) -> None:
    """Launch the Gleansight UI application."""
    config_path = Path(config) if config else None
    services = build_ui_services(
        config_path=config_path,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
    )
    run_app(services)


if __name__ == "__main__":
    main()
