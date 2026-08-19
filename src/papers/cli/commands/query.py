from __future__ import annotations

from typing import Annotated, Any

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
        if key == "value_numeric":
            try:
                constraints[key] = float(value)
            except ValueError as exc:
                raise typer.BadParameter("value_numeric must be a number") from exc
        elif key == "value_boolean":
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes"}:
                constraints[key] = 1
            elif lowered in {"0", "false", "no"}:
                constraints[key] = 0
            else:
                raise typer.BadParameter("value_boolean must be one of: true,false,1,0")
        else:
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
    field_path: Annotated[str, typer.Argument(help="Field path")],
    prompt_version_id: Annotated[str, typer.Option(help="Prompt version ID")],
    constraint: Annotated[
        list[str] | None, typer.Option(help="Constraint key=value", show_default=False)
    ] = None,
    latest_only: Annotated[bool, typer.Option(help="Only latest successful runs")] = True,
) -> None:
    container = cli_app.get_container()
    constraints = _parse_constraints(constraint or [])
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
    operation: str = typer.Option("count", help="Aggregation operation: count|average"),
    group_by: str | None = typer.Option(None, help="Field to group by when using average"),
    latest_only: bool = typer.Option(True, help="Only latest successful runs"),
) -> None:
    container = cli_app.get_container()
    op = operation.strip().lower()
    table = Table(title="Aggregation Results")
    if op == "count":
        counts = container.aggregate_extractions.count_by_value(
            field_path=field_path,
            prompt_version_id=prompt_version_id,
            latest_only=latest_only,
        )
        table.add_column("Value")
        table.add_column("Count")
        for value, count in sorted(counts.items()):
            table.add_row(str(value), str(count))
    elif op == "average":
        avg = container.aggregate_extractions.average_numeric(
            field_path=field_path,
            prompt_version_id=prompt_version_id,
            group_by=group_by,
            latest_only=latest_only,
        )
        if isinstance(avg, dict):
            table.add_column("Group")
            table.add_column("Average")
            for key, value in sorted(avg.items()):
                table.add_row(str(key), f"{value:.4f}")
        elif avg is None:
            table.add_column("Result")
            table.add_row("No numeric data")
        else:
            table.add_column("Average")
            table.add_row(f"{avg:.4f}")
    else:
        raise typer.BadParameter("operation must be one of: count, average")
    cli_app.console.print(table)
