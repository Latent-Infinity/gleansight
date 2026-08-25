from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from papers.app import use_cases
from papers.app.composition_root import build_container
from papers.config.settings import (
    DEFAULT_OLLAMA_BASE_URL,
    Settings,
    load_settings,
    packaged_defaults_path,
    public_configuration_error_message,
)
from papers.domain.errors import ConfigurationError
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import (
    PiccoloAtomicCandidateImport,
    PiccoloCandidateImporter,
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloPaperProjectStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)
console = Console()


@dataclass
class CLIContainer:
    settings: Settings
    discover: use_cases.DiscoverCandidatesUseCase
    import_candidate: use_cases.ImportCandidateUseCase
    get_candidate: Callable[[str], dict[str, Any] | None] | None
    run_analysis: use_cases.RunAnalysisUseCase
    analyze_project: use_cases.AnalyzeProjectUseCase
    job_runner: Any
    job_queue: Any
    search: use_cases.SearchPapersUseCase
    filter_extractions: use_cases.FilterByExtractionsUseCase
    aggregate_extractions: use_cases.AggregateExtractionsUseCase
    recover_jobs: use_cases.RecoverStuckJobsUseCase
    rebuild_index: use_cases.RebuildVectorIndexUseCase
    rebuild_fts: use_cases.RebuildTitleAbstractIndexUseCase
    synthesize_from_corpus: use_cases.SynthesizeFromCorpusUseCase


_cli_options: dict[str, Any] = {
    "config": None,
    "llm_base_url": DEFAULT_OLLAMA_BASE_URL,
    "llm_api_key": None,
}
_container: CLIContainer | None = None


@app.callback()
def main(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Settings override TOML")
    ] = None,
    llm_base_url: Annotated[
        str, typer.Option(help="Base URL for OpenAI-compatible LLM")
    ] = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: Annotated[str | None, typer.Option(help="LLM API key")] = None,
) -> None:
    _cli_options["config"] = config
    _cli_options["llm_base_url"] = llm_base_url
    _cli_options["llm_api_key"] = llm_api_key


def get_container() -> CLIContainer:
    global _container
    if _container is not None:
        return _container
    try:
        settings = load_settings(
            defaults_path=packaged_defaults_path(),
            override_path=_cli_options["config"],
        )
        base = build_container(
            settings,
            llm_base_url=_cli_options["llm_base_url"],
            llm_api_key=_cli_options["llm_api_key"],
        )
    except ConfigurationError as exc:
        console.print(public_configuration_error_message(exc))
        raise typer.Exit(code=1) from None

    candidate_store = getattr(base, "candidate_store", PiccoloCandidateStore())
    extraction_store = PiccoloExtractionStore()
    papers_fts = PiccoloPaperFTS()
    run_analysis = use_cases.RunAnalysisUseCase(
        job_queue=base.job_queue,
        prompt_store=base.prompt_store,
        profile_store=base.profile_store,
        analysis_store=base.analysis_store,
    )
    filter_extractions = use_cases.FilterByExtractionsUseCase(extraction_store=extraction_store)

    _container = CLIContainer(
        settings=settings,
        discover=use_cases.DiscoverCandidatesUseCase(
            scholar_client=base.scholar_client,
            candidate_store=candidate_store,
        ),
        import_candidate=use_cases.ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=base.paper_store,
            job_queue=base.job_queue,
            external_id_store=base.external_id_store,
            atomic_importer=PiccoloCandidateImporter(),
            project_store=PiccoloProjectStore(),
            tag_store=PiccoloTagStore(),
            atomic_candidate_import=PiccoloAtomicCandidateImport(),
        ),
        get_candidate=getattr(candidate_store, "get_candidate", None),
        run_analysis=run_analysis,
        analyze_project=use_cases.AnalyzeProjectUseCase(
            paper_project_store=PiccoloPaperProjectStore(),
            prompt_store=base.prompt_store,
            run_analysis=run_analysis,
            filter_extractions=filter_extractions,
        ),
        job_runner=base.job_runner,
        job_queue=base.job_queue,
        search=use_cases.SearchPapersUseCase(
            papers_fts=papers_fts,
            vector_index=base.vector_index,
            embedder=base.embedder,
        ),
        filter_extractions=filter_extractions,
        aggregate_extractions=use_cases.AggregateExtractionsUseCase(
            extraction_store=extraction_store
        ),
        recover_jobs=use_cases.RecoverStuckJobsUseCase(job_queue=base.job_queue),
        rebuild_index=use_cases.RebuildVectorIndexUseCase(
            paper_store=base.paper_store,
            blob_store=base.blob_store,
            embedder=base.embedder,
            vector_index=base.vector_index,
        ),
        rebuild_fts=use_cases.RebuildTitleAbstractIndexUseCase(
            rebuild=papers_fts.rebuild,
        ),
        synthesize_from_corpus=use_cases.SynthesizeFromCorpusUseCase(
            embedder=base.embedder,
            vector_index=base.vector_index,
            paper_store=base.paper_store,
            blob_store=base.blob_store,
            llm_client=base.llm_client,
            paper_project_store=PiccoloPaperProjectStore(),
        ),
    )
    return _container


# Command modules import this file; load them after `app` exists.
from papers.cli.commands import admin as admin_commands  # noqa: E402
from papers.cli.commands import discovery as discovery_commands  # noqa: E402
from papers.cli.commands import pipeline as pipeline_commands  # noqa: E402
from papers.cli.commands import query as query_commands  # noqa: E402
from papers.cli.commands import synthesis as synthesis_commands  # noqa: E402

app.add_typer(discovery_commands.app)
app.add_typer(pipeline_commands.app)
app.add_typer(query_commands.app)
app.add_typer(admin_commands.app)
app.add_typer(synthesis_commands.app)
