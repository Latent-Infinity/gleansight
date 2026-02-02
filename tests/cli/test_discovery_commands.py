from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import importlib

from typer.testing import CliRunner


@dataclass
class FakeDiscover:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def discover(self, query: str, filters: dict[str, Any], max_results: int):
        self.calls.append({"query": query, "filters": filters, "max_results": max_results})
        return ["cand-1", "cand-2"]


@dataclass
class FakeImport:
    calls: list[str] = field(default_factory=list)

    def import_candidate(self, candidate_id: str) -> str:
        self.calls.append(candidate_id)
        return "paper-1"


@dataclass
class FakeContainer:
    discover: FakeDiscover
    import_candidate: FakeImport


def test_discover_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(discover=FakeDiscover(), import_candidate=FakeImport())

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["discover", "transformer", "--max-results", "2"])

    assert result.exit_code == 0
    assert "Found 2 candidates" in result.output
    assert container.discover.calls[0]["query"] == "transformer"


def test_import_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(discover=FakeDiscover(), import_candidate=FakeImport())

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["import", "cand-1"])

    assert result.exit_code == 0
    assert "paper-1" in result.output
    assert container.import_candidate.calls == ["cand-1"]


def test_discover_with_year_filters(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(discover=FakeDiscover(), import_candidate=FakeImport())

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        ["discover", "transformer", "--year-min", "2020", "--year-max", "2024"],
    )

    assert result.exit_code == 0
    assert "Found 2 candidates" in result.output
    assert container.discover.calls[0]["filters"] == {"year_min": 2020, "year_max": 2024}
