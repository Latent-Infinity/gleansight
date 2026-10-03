from __future__ import annotations

from gleansight.api_cli import app as api_app
from nsqd.cli import app
from papers.cli.app import app as papers_app

app.add_typer(api_app, name="api")
app.add_typer(papers_app, name="papers")


def main() -> None:
    app()


__all__ = ["app", "main"]
