from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.table import Table

import papers.cli.app as cli_app
from papers.app.use_cases.analysis import ExtractionFilter
from papers.cli.commands.query import _parse_constraints

app = typer.Typer(add_completion=False)


def _normalize_model_name(model_name: str | None) -> str | None:
    if model_name is None:
        return None
    resolved = model_name.strip()
    if not resolved:
        raise typer.BadParameter("--model-name must not be blank")
    return resolved


@app.command("run-jobs")
def run_jobs(
    max_jobs: int = typer.Option(1, help="Maximum jobs to run (ignored in daemon mode)"),
    daemon: bool = typer.Option(False, help="Run continuously"),
    poll_interval: float = typer.Option(1.0, help="Seconds to sleep between polls"),
    max_iterations: int = typer.Option(0, help="Maximum daemon iterations (0 = infinite)"),
) -> None:
    container = cli_app.get_container()
    runner = container.job_runner
    if daemon:
        iterations = 0
        while True:
            ran = runner.run_next(datetime.now(UTC))
            if not ran:
                time.sleep(poll_interval)
            iterations += 1
            if max_iterations and iterations >= max_iterations:
                break
    else:
        ran = 0
        for _ in range(max_jobs):
            if not runner.run_next(datetime.now(UTC)):
                break
            ran += 1
        cli_app.console.print(f"Processed {ran} jobs")


@app.command("analyze")
def analyze(
    paper_id: str = typer.Argument(..., help="Paper ID"),
    prompt_id: str = typer.Option(..., help="Prompt ID"),
    prompt_version_id: str | None = typer.Option(None, help="Prompt version ID"),
    profile_id: str = typer.Option(..., help="Profile ID"),
    model_name: str | None = typer.Option(
        None, help="Model name (default: configured llm.default_model)"
    ),
    force: bool = typer.Option(False, help="Force new analysis run"),
) -> None:
    model_name = _normalize_model_name(model_name)
    container = cli_app.get_container()
    run_id = container.run_analysis(
        paper_id=paper_id,
        prompt_id=prompt_id,
        prompt_version_id=prompt_version_id,
        profile_id=profile_id,
        model_name=model_name or container.settings.llm.default_model,
        force=force,
    )
    cli_app.console.print(f"Analysis run queued: {run_id}")


@app.command("analyze-project")
def analyze_project(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    prompt_version_id: Annotated[str, typer.Option(help="Target prompt version ID")],
    profile_id: Annotated[str, typer.Option(help="Profile ID")],
    model_name: Annotated[
        str | None,
        typer.Option(help="Model name (default: configured llm.default_model)"),
    ] = None,
    label: Annotated[str | None, typer.Option(help="Optional membership label")] = None,
    field_path: Annotated[
        str | None, typer.Option(help="Extraction field path to filter on")
    ] = None,
    constraint: Annotated[
        list[str] | None, typer.Option(help="Constraint key=value", show_default=False)
    ] = None,
    filter_prompt_version_id: Annotated[
        str | None,
        typer.Option(help="Prompt version whose extractions are queried"),
    ] = None,
    force: Annotated[bool, typer.Option(help="Force new analysis runs")] = False,
) -> None:
    model_name = _normalize_model_name(model_name)
    if constraint and field_path is None:
        raise typer.BadParameter("--field-path is required when --constraint is set")
    filters = None
    if field_path is not None:
        filters = [
            ExtractionFilter(
                field_path=field_path,
                prompt_version_id=filter_prompt_version_id or prompt_version_id,
                constraints=_parse_constraints(constraint or []),
            )
        ]
    container = cli_app.get_container()
    try:
        run_ids = container.analyze_project(
            project_id=project_id,
            prompt_version_id=prompt_version_id,
            profile_id=profile_id,
            model_name=model_name or container.settings.llm.default_model,
            label=label,
            filters=filters,
            force=force,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    cli_app.console.print(f"Queued {len(run_ids)} analysis runs")
    for run_id in run_ids:
        cli_app.console.print(run_id)


@app.command("status")
def status(limit: int = typer.Option(50, help="Max jobs to show")) -> None:
    container = cli_app.get_container()
    job_queue = container.job_queue
    if not hasattr(job_queue, "list_jobs"):
        cli_app.console.print("Job status unavailable")
        raise typer.Exit(code=1)
    jobs = job_queue.list_jobs(limit=limit)
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1
    table = Table(title="Job Queue Status")
    table.add_column("Status")
    table.add_column("Count")
    for status_name, count in sorted(counts.items()):
        table.add_row(status_name, str(count))
    cli_app.console.print(table)
