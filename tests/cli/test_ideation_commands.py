from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from typer.testing import CliRunner


@dataclass
class FakeWorkflow:
    output: Path
    calls: list[Any] = field(default_factory=list)
    error: ValueError | None = None

    def run(self, request: Any) -> Path:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.output


@dataclass
class FakeProfileStore:
    profile: dict[str, Any] | None = field(
        default_factory=lambda: {"profile_id": "default", "base_url": "http://localhost:11434"}
    )

    def get(self, profile_id: str) -> dict[str, Any] | None:
        return self.profile


@dataclass
class FakeLLMSettings:
    default_profile: str = "default"
    default_model: str = "local-model"


@dataclass
class FakeSettings:
    llm: FakeLLMSettings = field(default_factory=FakeLLMSettings)


@dataclass
class FakeContainer:
    ideate_project: FakeWorkflow
    plan_idea: FakeWorkflow
    profile_store: FakeProfileStore = field(default_factory=FakeProfileStore)
    settings: FakeSettings = field(default_factory=FakeSettings)


def test_ideate_project_help_lists_limits() -> None:
    cli_app = importlib.import_module("papers.cli.app")

    result = CliRunner().invoke(cli_app.app, ["ideate-project", "--help"])

    assert result.exit_code == 0
    assert "--max-papers" in result.output
    assert "--critic-model" in result.output


def test_ideate_project_routes_configured_profile_and_model(monkeypatch, tmp_path: Path) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    workflow = FakeWorkflow(tmp_path / "bundle")
    container = FakeContainer(workflow, FakeWorkflow(tmp_path / "plan"))
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = CliRunner().invoke(cli_app.app, ["ideate-project", "project-1", "Find a gap"])

    assert result.exit_code == 0
    assert "Ideation bundle:" in result.output
    assert "test_ideate_project_routes_con0/bundle" in result.output.replace("\n", "")
    assert workflow.calls[0].model == "local-model"
    assert workflow.calls[0].profile["profile_id"] == "default"


def test_plan_idea_rejects_missing_profile(monkeypatch, tmp_path: Path) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    container = FakeContainer(
        FakeWorkflow(tmp_path / "bundle"),
        FakeWorkflow(tmp_path / "plan"),
        profile_store=FakeProfileStore(profile=None),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = CliRunner().invoke(cli_app.app, ["plan-idea", str(tmp_path / "bundle"), "idea-1"])

    assert result.exit_code == 1
    assert "profile not found: default" in result.output
    assert container.plan_idea.calls == []


def test_ideate_project_reports_workflow_failure(monkeypatch, tmp_path: Path) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    workflow = FakeWorkflow(tmp_path / "bundle", error=ValueError("invalid ideation"))
    container = FakeContainer(workflow, FakeWorkflow(tmp_path / "plan"))
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = CliRunner().invoke(cli_app.app, ["ideate-project", "project-1", "Find a gap"])

    assert result.exit_code == 1
    assert "invalid ideation" in result.output


def test_plan_idea_reports_workflow_failure(monkeypatch, tmp_path: Path) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    workflow = FakeWorkflow(tmp_path / "plan", error=ValueError("invalid plan"))
    container = FakeContainer(FakeWorkflow(tmp_path / "bundle"), workflow)
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = CliRunner().invoke(cli_app.app, ["plan-idea", str(tmp_path / "bundle"), "idea-1"])

    assert result.exit_code == 1
    assert "invalid plan" in result.output
