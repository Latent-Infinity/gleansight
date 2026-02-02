from __future__ import annotations

from dataclasses import dataclass, field

import importlib

from typer.testing import CliRunner


@dataclass
class FakeSearch:
    calls: list[dict[str, int | str]] = field(default_factory=list)

    def search(self, query: str, limit: int):
        self.calls.append({"query": query, "limit": limit})
        return [{"paper_id": "paper-1", "score": 0.9}]


@dataclass
class FakeFilter:
    calls: list[dict] = field(default_factory=list)

    def filter(self, field_path: str, prompt_version_id: str, constraints: dict, latest_only: bool = True):
        self.calls.append(
            {
                "field_path": field_path,
                "prompt_version_id": prompt_version_id,
                "constraints": constraints,
            }
        )
        return ["paper-1", "paper-2"]


@dataclass
class FakeAggregate:
    calls: list[dict[str, str]] = field(default_factory=list)

    def count_by_value(self, field_path: str, prompt_version_id: str, latest_only: bool = True):
        self.calls.append({"field_path": field_path, "prompt_version_id": prompt_version_id})
        return {"value": 2}


@dataclass
class FakeContainer:
    search: FakeSearch
    filter_extractions: FakeFilter
    aggregate_extractions: FakeAggregate


def test_query_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate())
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["query", "transformer", "--limit", "1"])

    assert result.exit_code == 0
    assert "paper-1" in result.output
    assert container.search.calls[0]["query"] == "transformer"


def test_filter_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate())
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "filter",
            "field",
            "--prompt-version-id",
            "pv1",
            "--constraint",
            "value_text=transformer",
        ],
    )

    assert result.exit_code == 0
    assert "Matched 2 papers" in result.output
    assert container.filter_extractions.calls[0]["constraints"] == {"value_text": "transformer"}


def test_aggregate_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate())
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "aggregate",
            "field",
            "--prompt-version-id",
            "pv1",
        ],
    )

    assert result.exit_code == 0
    assert "value" in result.output


def test_filter_with_invalid_constraint(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate())
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "filter",
            "field",
            "--prompt-version-id",
            "pv1",
            "--constraint",
            "invalid_format",
        ],
    )

    assert result.exit_code != 0
    assert "constraints must be key=value" in result.output
