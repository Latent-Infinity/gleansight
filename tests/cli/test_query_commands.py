from __future__ import annotations

import importlib
from dataclasses import dataclass, field

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

    def filter(
        self, field_path: str, prompt_version_id: str, constraints: dict, latest_only: bool = True
    ):
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
        self.calls.append(
            {
                "operation": "count",
                "field_path": field_path,
                "prompt_version_id": prompt_version_id,
            }
        )
        return {"value": 2}

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ):
        self.calls.append(
            {
                "operation": "average",
                "field_path": field_path,
                "prompt_version_id": prompt_version_id,
                "group_by": group_by or "",
            }
        )
        if group_by:
            return {"2023": 3.5}
        return 2.75


@dataclass
class FakeContainer:
    search: FakeSearch
    filter_extractions: FakeFilter
    aggregate_extractions: FakeAggregate


def test_query_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate()
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["query", "transformer", "--limit", "1"])

    assert result.exit_code == 0
    assert "paper-1" in result.output
    assert container.search.calls[0]["query"] == "transformer"


def test_filter_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate()
    )
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
    container = FakeContainer(
        search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate()
    )
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
    assert container.aggregate_extractions.calls[0]["operation"] == "count"


def test_filter_with_invalid_constraint(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(), filter_extractions=FakeFilter(), aggregate_extractions=FakeAggregate()
    )
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


def test_filter_parses_numeric_and_boolean_constraints(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "filter",
            "field",
            "--prompt-version-id",
            "pv1",
            "--constraint",
            "value_numeric=3.14",
            "--constraint",
            "value_boolean=true",
        ],
    )

    assert result.exit_code == 0
    constraints = container.filter_extractions.calls[0]["constraints"]
    assert constraints["value_numeric"] == 3.14
    assert constraints["value_boolean"] == 1


def test_filter_rejects_invalid_numeric_constraint(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "filter",
            "field",
            "--prompt-version-id",
            "pv1",
            "--constraint",
            "value_numeric=not-a-number",
        ],
    )

    assert result.exit_code != 0
    assert "value_numeric must be a number" in result.output


def test_aggregate_average_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "aggregate",
            "rigor_score",
            "--prompt-version-id",
            "pv1",
            "--operation",
            "average",
        ],
    )

    assert result.exit_code == 0
    assert "2.7500" in result.output
    assert container.aggregate_extractions.calls[0]["operation"] == "average"


def test_aggregate_average_grouped_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "aggregate",
            "rigor_score",
            "--prompt-version-id",
            "pv1",
            "--operation",
            "average",
            "--group-by",
            "year",
        ],
    )

    assert result.exit_code == 0
    assert "2023" in result.output
    assert "3.5000" in result.output


def test_aggregate_rejects_invalid_operation(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "aggregate",
            "field",
            "--prompt-version-id",
            "pv1",
            "--operation",
            "median",
        ],
    )

    assert result.exit_code != 0
    assert "operation must be one of: count, average" in result.output
