from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from typer.testing import CliRunner

from papers.domain import InvestigationPlan, render_investigation_plan_markdown
from tests.investigation_plan_test_data import valid_investigation_plan_payload


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
        return ["paper-1"]


@dataclass
class FakeAggregate:
    calls: list[dict[str, str]] = field(default_factory=list)

    def count_by_value(self, field_path: str, prompt_version_id: str, latest_only: bool = True):
        self.calls.append({"operation": "count", "field_path": field_path})
        return {"value": 1}

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ):
        self.calls.append({"operation": "average", "field_path": field_path})
        return 2.5


@dataclass
class FakeSynthesize:
    answer: str = "The answer based on the corpus."
    sources: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"paper_id": "paper-1", "title": "Paper Alpha"},
            {"paper_id": "paper-2", "title": "Paper Beta"},
        ]
    )
    mock_exception: type[Exception] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def synthesize(
        self,
        question: str,
        project_id: str | None = None,
        tags: list[str] | None = None,
        num_retrieved_docs: int = 5,
        llm_profile: dict[str, Any] | None = None,
        llm_model: str = "gpt-4o-mini",
        investigation_plan: bool = False,
    ) -> tuple[str, list[dict[str, Any]]]:
        self.calls.append(
            {
                "question": question,
                "project_id": project_id,
                "tags": tags,
                "num_retrieved_docs": num_retrieved_docs,
                "llm_model": llm_model,
                "investigation_plan": investigation_plan,
            }
        )
        if self.mock_exception:
            raise self.mock_exception("Synthesis error")
        return self.answer, self.sources


@dataclass
class FakeContainer:
    search: FakeSearch
    filter_extractions: FakeFilter
    aggregate_extractions: FakeAggregate
    synthesize_from_corpus: FakeSynthesize


def test_ask_command(monkeypatch) -> None:
    """The ask command calls synthesize and prints the answer."""
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["ask", "What is attention?"])

    assert result.exit_code == 0
    assert "The answer based on the corpus." in result.output
    assert synth.calls[0]["question"] == "What is attention?"


def test_ask_command_shows_sources(monkeypatch) -> None:
    """The ask command lists source papers."""
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["ask", "Tell me about papers"])

    assert result.exit_code == 0
    assert "Paper Alpha" in result.output
    assert "Paper Beta" in result.output
    assert "paper-1" in result.output
    assert "paper-2" in result.output


def test_ask_command_with_project_flag(monkeypatch) -> None:
    """The --project flag is passed to the use case."""
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        ["ask", "What is attention?", "--project", "proj-1"],
    )

    assert result.exit_code == 0
    assert synth.calls[0]["project_id"] == "proj-1"


def test_ask_command_with_num_docs_flag(monkeypatch) -> None:
    """The --num-docs flag controls how many documents are retrieved."""
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize()
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        ["ask", "How many docs?", "--num-docs", "10"],
    )

    assert result.exit_code == 0
    assert synth.calls[0]["num_retrieved_docs"] == 10


def test_ask_command_handles_error(monkeypatch) -> None:
    """Synthesis errors are caught and printed."""
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize(mock_exception=RuntimeError)
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["ask", "Fail please"])

    assert result.exit_code == 1
    assert "Synthesis error" in result.output


def test_ask_command_no_sources(monkeypatch) -> None:
    """When no sources are returned, no sources table is printed."""
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize(answer="No relevant documents found.", sources=[])
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["ask", "Nothing here"])

    assert result.exit_code == 0
    assert "No relevant documents found." in result.output


def test_ask_command_investigation_plan_mode(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize(answer="# Investigation Plan")
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        ["ask", "Plan the next study", "--investigation-plan"],
    )

    assert result.exit_code == 0
    assert "Investigation Plan" in result.output
    assert synth.calls[0]["investigation_plan"] is True


def test_ask_command_investigation_plan_preserves_bracketed_metadata(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    report = render_investigation_plan_markdown(
        InvestigationPlan.model_validate(valid_investigation_plan_payload())
    )
    synth = FakeSynthesize(answer=report)
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["ask", "Plan study", "--investigation-plan"])

    assert result.exit_code == 0
    assert "[not_started]" in result.output
    assert "paper-1" in result.output
    assert "[fact/reported; sources: paper-1" in result.output
    assert "basis: Assumes one pilot run" in result.output
    assert "single comparable GPU." in result.output


def test_ask_command_plain_answer_keeps_rich_markup_behavior(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    synth = FakeSynthesize(answer="[bold]Ordinary answer[/bold]")
    container = FakeContainer(
        search=FakeSearch(),
        filter_extractions=FakeFilter(),
        aggregate_extractions=FakeAggregate(),
        synthesize_from_corpus=synth,
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["ask", "Normal question"])

    assert result.exit_code == 0
    assert "Ordinary answer" in result.output
    assert "[bold]" not in result.output
