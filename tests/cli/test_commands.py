from __future__ import annotations

from typer.testing import CliRunner

from papers.cli.app import app


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in [
        "discover",
        "import",
        "run-jobs",
        "analyze",
        "status",
        "query",
        "filter",
        "aggregate",
        "recover-jobs",
        "rebuild-index",
        "rebuild-fts",
    ]:
        assert command in result.output
