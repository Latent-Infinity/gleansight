from __future__ import annotations

import typer

import papers.cli.app as cli_app

app = typer.Typer(add_completion=False)


@app.command("recover-jobs")
def recover_jobs() -> None:
    container = cli_app.get_container()
    recovered = container.recover_jobs()
    cli_app.console.print(f"Recovered {len(recovered)} jobs")


@app.command("rebuild-index")
def rebuild_index() -> None:
    container = cli_app.get_container()
    count = container.rebuild_index()
    cli_app.console.print(f"Rebuilt vector index for {count} papers")


@app.command("rebuild-fts")
def rebuild_fts() -> None:
    container = cli_app.get_container()
    count = container.rebuild_fts()
    cli_app.console.print(f"Rebuilt title/abstract index for {count} papers")
