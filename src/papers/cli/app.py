from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from papers.app import use_cases
from papers.app.composition_root import build_container
from papers.config.settings import load_settings
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import PiccoloCandidateStore, PiccoloExtractionStore

app = typer.Typer(add_completion=False)
console = Console()


@dataclass
class CLIContainer:
    discover: use_cases.DiscoverCandidatesUseCase
    import_candidate: use_cases.ImportCandidateUseCase
    run_analysis: use_cases.RunAnalysisUseCase
    job_runner: Any
    job_queue: Any
    search: use_cases.SearchPapersUseCase
    filter_extractions: use_cases.FilterByExtractionsUseCase
    aggregate_extractions: use_cases.AggregateExtractionsUseCase
    recover_jobs: use_cases.RecoverStuckJobsUseCase
    rebuild_index: use_cases.RebuildVectorIndexUseCase


_cli_options: dict[str, Any] = {
    "config": None,
    "llm_base_url": "http://localhost:8000",
    "llm_api_key": None,
}
_container: CLIContainer | None = None


@app.callback()
def main(
    config: Path | None = typer.Option(None, "--config", "-c", help="Settings override TOML"),
    llm_base_url: str = typer.Option(
        "http://localhost:8000", help="Base URL for OpenAI-compatible LLM"
    ),
    llm_api_key: str | None = typer.Option(None, help="LLM API key"),
) -> None:
    _cli_options["config"] = config
    _cli_options["llm_base_url"] = llm_base_url
    _cli_options["llm_api_key"] = llm_api_key


def get_container() -> CLIContainer:
    global _container
    if _container is not None:
        return _container
    defaults_path = Path(__file__).resolve().parents[1] / "config" / "defaults.toml"
    settings = load_settings(defaults_path=defaults_path, override_path=_cli_options["config"])
    base = build_container(
        settings,
        llm_base_url=_cli_options["llm_base_url"],
        llm_api_key=_cli_options["llm_api_key"],
    )

    candidate_store = PiccoloCandidateStore()
    extraction_store = PiccoloExtractionStore()
    papers_fts = PiccoloPaperFTS()

    _container = CLIContainer(
        discover=use_cases.DiscoverCandidatesUseCase(
            scholar_client=base.scholar_client,
            candidate_store=candidate_store,
        ),
        import_candidate=use_cases.ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=base.paper_store,
            job_queue=base.job_queue,
        ),
        run_analysis=use_cases.RunAnalysisUseCase(
            job_queue=base.job_queue,
            prompt_store=base.prompt_store,
            profile_store=base.profile_store,
            analysis_store=base.analysis_store,
        ),
        job_runner=base.job_runner,
        job_queue=base.job_queue,
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
        recover_jobs=use_cases.RecoverStuckJobsUseCase(job_queue=base.job_queue),
        rebuild_index=use_cases.RebuildVectorIndexUseCase(
            paper_store=base.paper_store,
            blob_store=base.blob_store,
            embedder=base.embedder,
            vector_index=base.vector_index,
        ),
    )
    return _container


from papers.cli.commands import admin as admin_commands
from papers.cli.commands import discovery as discovery_commands
from papers.cli.commands import pipeline as pipeline_commands
from papers.cli.commands import query as query_commands

app.add_typer(discovery_commands.app)
app.add_typer(pipeline_commands.app)
app.add_typer(query_commands.app)
app.add_typer(admin_commands.app)
