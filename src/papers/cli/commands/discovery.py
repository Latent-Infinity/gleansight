from __future__ import annotations

from typing import Any

import typer
from rich.table import Table

import papers.cli.app as cli_app

app = typer.Typer(add_completion=False)


@app.command("discover")
def discover(
    query: str = typer.Argument(..., help="Search query"),
    max_results: int = typer.Option(50, help="Maximum results"),
    year_min: int | None = typer.Option(None, help="Minimum year"),
    year_max: int | None = typer.Option(None, help="Maximum year"),
    include_paywalled: bool = typer.Option(
        False,
        "--include-paywalled",
        help="Include papers without open access PDFs (overrides config)",
    ),
) -> None:
    container = cli_app.get_container()
    filters: dict[str, Any] = {}
    if year_min is not None:
        filters["year_min"] = year_min
    if year_max is not None:
        filters["year_max"] = year_max

    # Apply open access filter from settings (unless overridden)
    if not include_paywalled and container.settings.scholar.require_open_access:
        filters["open_access_pdf"] = True

    candidate_ids = container.discover.discover(query=query, filters=filters, max_results=max_results)
    table = Table(title="Discovery Results")
    table.add_column("Candidate ID")
    for candidate_id in candidate_ids:
        table.add_row(candidate_id)
    cli_app.console.print(table)
    cli_app.console.print(f"Found {len(candidate_ids)} candidates")


@app.command("import")
def import_candidate(candidate_id: str = typer.Argument(..., help="Candidate ID")) -> None:
    container = cli_app.get_container()
    paper_id = container.import_candidate.import_candidate(candidate_id=candidate_id)
    cli_app.console.print(f"Imported candidate {candidate_id} as paper {paper_id}")
