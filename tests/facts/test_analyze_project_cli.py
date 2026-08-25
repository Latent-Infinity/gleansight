from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from click import Group
from typer.main import get_command
from typer.testing import CliRunner

from papers.app.use_cases.analysis import ExtractionFilter

CONFIGURED_DEFAULT_MODEL = "configured-project-analysis-model"


@dataclass
class FakeAnalyzeProject:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(
        self,
        *,
        project_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
        label: str | None = None,
        filters: list[ExtractionFilter] | None = None,
        force: bool = False,
    ) -> list[str]:
        self.calls.append(
            {
                "project_id": project_id,
                "prompt_version_id": prompt_version_id,
                "profile_id": profile_id,
                "model_name": model_name,
                "label": label,
                "filters": filters,
                "force": force,
            }
        )
        return ["run-1"]


@dataclass
class FakeLLMSettings:
    default_model: str = CONFIGURED_DEFAULT_MODEL


@dataclass
class FakeSettings:
    llm: FakeLLMSettings = field(default_factory=FakeLLMSettings)


@dataclass
class FakeContainer:
    analyze_project: Any
    settings: FakeSettings = field(default_factory=FakeSettings)


@dataclass
class RejectingAnalyzeProject:
    def __call__(self, **kwargs: Any) -> list[str]:
        raise ValueError("unsupported extraction constraint field: entity_type")


def test_analyze_project_help_lists_flags() -> None:
    cli_app = importlib.import_module("papers.cli.app")
    width = 200
    result = CliRunner().invoke(
        cli_app.app,
        ["analyze-project", "--help"],
        terminal_width=width,
        env={"COLUMNS": str(width), "TERMINAL_WIDTH": str(width)},
    )
    assert result.exit_code == 0, result.output
    click_app = get_command(cli_app.app)
    assert isinstance(click_app, Group)
    command = click_app.commands["analyze-project"]
    opts = {opt for param in command.params for opt in param.opts}
    for flag in (
        "--prompt-version-id",
        "--profile-id",
        "--model-name",
        "--label",
        "--field-path",
        "--constraint",
        "--filter-prompt-version-id",
        "--force",
    ):
        assert flag in opts, flag


def test_analyze_project_forwards_extraction_filter(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake = FakeAnalyzeProject()
    monkeypatch.setattr(cli_app, "get_container", lambda: FakeContainer(analyze_project=fake))
    result = CliRunner().invoke(
        cli_app.app,
        [
            "analyze-project",
            "proj-1",
            "--prompt-version-id",
            "pv-target",
            "--profile-id",
            "profile",
            "--model-name",
            "model",
            "--label",
            "primary",
            "--field-path",
            "algorithm_family",
            "--constraint",
            "value_text=transformer",
            "--filter-prompt-version-id",
            "pv-filter",
            "--force",
        ],
    )
    assert result.exit_code == 0, result.output
    assert fake.calls == [
        {
            "project_id": "proj-1",
            "prompt_version_id": "pv-target",
            "profile_id": "profile",
            "model_name": "model",
            "label": "primary",
            "filters": [
                ExtractionFilter(
                    field_path="algorithm_family",
                    prompt_version_id="pv-filter",
                    constraints={"value_text": "transformer"},
                )
            ],
            "force": True,
        }
    ]


def test_analyze_project_defaults_filter_prompt_version(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake = FakeAnalyzeProject()
    monkeypatch.setattr(cli_app, "get_container", lambda: FakeContainer(analyze_project=fake))
    result = CliRunner().invoke(
        cli_app.app,
        [
            "analyze-project",
            "proj-1",
            "--prompt-version-id",
            "pv-target",
            "--profile-id",
            "profile",
            "--model-name",
            "model",
            "--field-path",
            "algorithm_family",
            "--constraint",
            "value_numeric=1.5",
            "--constraint",
            "value_boolean=1",
        ],
    )
    assert result.exit_code == 0, result.output
    filt = fake.calls[0]["filters"][0]
    assert filt.prompt_version_id == "pv-target"
    assert filt.constraints == {"value_numeric": 1.5, "value_boolean": 1}


def test_analyze_project_without_field_path_sends_no_filters(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake = FakeAnalyzeProject()
    monkeypatch.setattr(cli_app, "get_container", lambda: FakeContainer(analyze_project=fake))
    result = CliRunner().invoke(
        cli_app.app,
        [
            "analyze-project",
            "proj-1",
            "--prompt-version-id",
            "pv-target",
            "--profile-id",
            "profile",
            "--model-name",
            "model",
        ],
    )
    assert result.exit_code == 0, result.output
    assert fake.calls[0]["filters"] is None
    assert fake.calls[0]["force"] is False


def test_analyze_project_defaults_model_name_to_configured_settings_value(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake = FakeAnalyzeProject()
    monkeypatch.setattr(cli_app, "get_container", lambda: FakeContainer(analyze_project=fake))
    result = CliRunner().invoke(
        cli_app.app,
        [
            "analyze-project",
            "proj-1",
            "--prompt-version-id",
            "pv-target",
            "--profile-id",
            "profile",
        ],
    )
    assert result.exit_code == 0, result.output
    assert fake.calls[0]["model_name"] == CONFIGURED_DEFAULT_MODEL


def test_analyze_project_reports_invalid_filter_without_traceback(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    monkeypatch.setattr(
        cli_app,
        "get_container",
        lambda: FakeContainer(analyze_project=RejectingAnalyzeProject()),
    )
    result = CliRunner().invoke(
        cli_app.app,
        [
            "analyze-project",
            "proj-1",
            "--prompt-version-id",
            "pv-target",
            "--profile-id",
            "profile",
            "--model-name",
            "model",
            "--field-path",
            "algorithm_family",
            "--constraint",
            "entity_type=paper",
        ],
    )

    assert result.exit_code == 2
    assert "unsupported extraction constraint field: entity_type" in result.output
    assert "Traceback" not in result.output
