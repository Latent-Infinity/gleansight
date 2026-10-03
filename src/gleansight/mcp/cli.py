from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from gleansight.api import ApiConfiguration, GleansightAPI
from gleansight.mcp.adapter import ToolSelection
from gleansight.mcp.server import serve

app = typer.Typer(add_completion=False, help="Serve the local operation registry over MCP stdio.")


@app.command()
def main(
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
    config: Annotated[Path | None, typer.Option("--config")] = None,
    nsqd_db: Annotated[Path | None, typer.Option("--nsqd-db")] = None,
    nsqd_index: Annotated[Path | None, typer.Option("--nsqd-index")] = None,
    namespace: Annotated[list[str] | None, typer.Option("--namespace")] = None,
    tool: Annotated[list[str] | None, typer.Option("--tool")] = None,
    allow_approvals: Annotated[bool, typer.Option("--allow-approvals")] = False,
) -> None:
    configuration = ApiConfiguration(
        repo_root=repo_root,
        config_path=config,
        nsqd_db=nsqd_db,
        nsqd_index=nsqd_index,
        allow_approvals=allow_approvals,
    )
    selection = ToolSelection(namespaces=tuple(namespace or ()), names=tuple(tool or ()))
    try:
        asyncio.run(serve(GleansightAPI(configuration), selection))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
