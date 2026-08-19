from __future__ import annotations

import typer
from rich.table import Table

import papers.cli.app as cli_app

app = typer.Typer(add_completion=False)


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Question to answer from the paper corpus"),
    project: str | None = typer.Option(None, help="Scope to a specific project ID"),
    num_docs: int = typer.Option(5, help="Number of documents to retrieve for context"),
    model: str = typer.Option("gpt-4o-mini", help="LLM model to use"),
) -> None:
    container = cli_app.get_container()
    try:
        answer, sources = container.synthesize_from_corpus.synthesize(
            question=question,
            project_id=project,
            num_retrieved_docs=num_docs,
            llm_model=model,
        )
    except Exception as exc:
        cli_app.console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    cli_app.console.print()
    cli_app.console.print(answer)

    if sources:
        cli_app.console.print()
        table = Table(title="Sources")
        table.add_column("Paper ID")
        table.add_column("Title")
        for source in sources:
            table.add_row(source.get("paper_id", ""), source.get("title", "Untitled"))
        cli_app.console.print(table)
