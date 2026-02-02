from __future__ import annotations

import time
from datetime import UTC, datetime

import typer
from rich.table import Table

import papers.cli.app as cli_app

app = typer.Typer(add_completion=False)


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
    model_name: str = typer.Option(..., help="Model name"),
    force: bool = typer.Option(False, help="Force new analysis run"),
) -> None:
    container = cli_app.get_container()
    run_id = container.run_analysis(
        paper_id=paper_id,
        prompt_id=prompt_id,
        prompt_version_id=prompt_version_id,
        profile_id=profile_id,
        model_name=model_name,
        force=force,
    )
    cli_app.console.print(f"Analysis run queued: {run_id}")


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
