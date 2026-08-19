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
    page_size: int | None = typer.Option(
        None,
        help="Page size for upstream API pagination (1-100). Defaults to max_results cap.",
    ),
    year_min: int | None = typer.Option(None, help="Minimum year"),
    year_max: int | None = typer.Option(None, help="Maximum year"),
    publication_types: str | None = typer.Option(
        None,
        help="Comma-separated publication types (e.g. Journal,Conference)",
    ),
    fields_of_study: str | None = typer.Option(
        None,
        help="Comma-separated fields of study",
    ),
    venue: str | None = typer.Option(
        None,
        help="Venue name filter",
    ),
    min_citation_count: int | None = typer.Option(
        None,
        help="Minimum citation count",
    ),
    publication_date_or_year: str | None = typer.Option(
        None,
        help="Publication date/year filter accepted by Semantic Scholar",
    ),
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
    if publication_types:
        filters["publication_types"] = publication_types
    if fields_of_study:
        filters["fields_of_study"] = fields_of_study
    if venue:
        filters["venue"] = venue
    if min_citation_count is not None:
        filters["min_citation_count"] = min_citation_count
    if publication_date_or_year:
        filters["publication_date_or_year"] = publication_date_or_year

    # Apply open access filter from settings (unless overridden)
    if not include_paywalled and container.settings.scholar.require_open_access:
        filters["open_access_pdf"] = True

    try:
        candidate_ids = container.discover.discover(
            query=query,
            filters=filters,
            max_results=max_results,
            page_size=page_size,
        )
    except Exception as exc:
        cli_app.console.print(f"Discover failed: {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Discovery Results")
    table.add_column("Candidate ID")
    table.add_column("Title")
    table.add_column("Year")
    table.add_column("Venue")
    get_candidate = container.get_candidate
    for candidate_id in candidate_ids:
        title = "-"
        year = "-"
        venue_name = "-"
        if get_candidate is not None:
            row = get_candidate(candidate_id)
            if row is not None:
                title = str(row.get("title") or "-")
                year_raw = row.get("year")
                year = str(year_raw) if year_raw is not None else "-"
                venue_name = str(row.get("venue") or "-")
        table.add_row(candidate_id, title, year, venue_name)
    cli_app.console.print(table)
    cli_app.console.print(f"Found {len(candidate_ids)} candidates")


@app.command("import")
def import_candidate(candidate_id: str = typer.Argument(..., help="Candidate ID")) -> None:
    container = cli_app.get_container()
    try:
        paper_id = container.import_candidate.import_candidate(candidate_id=candidate_id)
    except Exception as exc:
        cli_app.console.print(f"Import failed for {candidate_id}: {exc}")
        raise typer.Exit(code=1) from exc
    cli_app.console.print(f"Imported candidate {candidate_id} as paper {paper_id}")
