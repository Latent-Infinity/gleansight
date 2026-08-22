from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml

from nsqd.domain.harvest import HarvestRejected
from nsqd.harvest import run_harvest
from nsqd.project_runtime import run_project
from nsqd.skeleton import run_skeleton

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def _root() -> None:
    """NS/QD-inspired discovery commands."""


@app.command()
def skeleton(
    candidate_fixture: Annotated[
        Path,
        typer.Option("--candidate-fixture", exists=True, readable=True),
    ],
    axiom: Annotated[str, typer.Option("--axiom")],
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
) -> None:
    try:
        result = run_skeleton(
            fixture_path=candidate_fixture,
            axiom=axiom,
            db_path=db,
            index_path=index,
        )
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    decision = result["card"]["card_decision"]
    viability = result["viability"]
    archive_state = "archive_empty" if result["archive_empty"] else "archive_has_elite"
    typer.echo(f"{decision} viability={viability} {archive_state} snapshot={result['snapshot_id']}")


@app.command()
def harvest(
    file: Annotated[Path, typer.Option("--file", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
) -> None:
    try:
        result = run_harvest(file_path=file, db_path=db, index_path=index)
    except HarvestRejected as exc:
        typer.echo(f"rejected: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    count = len(result["record_ids"])
    typer.echo(f"accepted {count} records")


@app.command()
def project(
    projection: Annotated[Path, typer.Option("--projection", exists=True, readable=True)],
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
) -> None:
    try:
        result = run_project(
            projection_path=projection,
            manifest_path=manifest,
            db_path=db,
            index_path=index,
        )
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        "projected "
        f"record={result['record_id']} "
        f"created={result['created']} "
        f"snapshot={result['snapshot_id']}"
    )


def main() -> None:
    app()
