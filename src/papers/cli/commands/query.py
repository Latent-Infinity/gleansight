from __future__ import annotations

from typing import Any

import typer
from rich.table import Table

import papers.cli.app as cli_app

app = typer.Typer(add_completion=False)


def _parse_constraints(values: list[str]) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise typer.BadParameter("constraints must be key=value")
        key, value = item.split("=", 1)
        constraints[key] = value
    return constraints


@app.command("query")
def query(
    query_text: str = typer.Argument(..., help="Query text"),
    limit: int = typer.Option(10, help="Max results"),
) -> None:
    container = cli_app.get_container()
    results = container.search.search(query=query_text, limit=limit)
    table = Table(title="Search Results")
    table.add_column("Paper ID")
    table.add_column("Score")
    for row in results:
        table.add_row(row["paper_id"], f"{row['score']:.4f}")
    cli_app.console.print(table)


@app.command("filter")
def filter_extractions(
    field_path: str = typer.Argument(..., help="Field path"),
    prompt_version_id: str = typer.Option(..., help="Prompt version ID"),
    constraint: list[str] = typer.Option([], help="Constraint key=value", show_default=False),
    latest_only: bool = typer.Option(True, help="Only latest successful runs"),
) -> None:
    container = cli_app.get_container()
    constraints = _parse_constraints(constraint)
    paper_ids = container.filter_extractions.filter(
        field_path=field_path,
        prompt_version_id=prompt_version_id,
        constraints=constraints,
        latest_only=latest_only,
    )
    table = Table(title="Filtered Papers")
    table.add_column("Paper ID")
    for paper_id in paper_ids:
        table.add_row(paper_id)
    cli_app.console.print(table)
    cli_app.console.print(f"Matched {len(paper_ids)} papers")


@app.command("aggregate")
def aggregate(
    field_path: str = typer.Argument(..., help="Field path"),
    prompt_version_id: str = typer.Option(..., help="Prompt version ID"),
    latest_only: bool = typer.Option(True, help="Only latest successful runs"),
) -> None:
    container = cli_app.get_container()
    counts = container.aggregate_extractions.count_by_value(
        field_path=field_path,
        prompt_version_id=prompt_version_id,
        latest_only=latest_only,
    )
    table = Table(title="Aggregation Results")
    table.add_column("Value")
    table.add_column("Count")
    for value, count in sorted(counts.items()):
        table.add_row(str(value), str(count))
    cli_app.console.print(table)
