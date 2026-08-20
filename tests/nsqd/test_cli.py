from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import nsqd.__main__ as main_module
from nsqd import cli as cli_module
from nsqd.cli import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"


def test_module_main_invokes_app(monkeypatch) -> None:
    called = {"ok": False}

    def fake_app() -> None:
        called["ok"] = True

    monkeypatch.setattr(main_module, "app", fake_app)
    monkeypatch.setattr(cli_module, "app", fake_app)
    main_module.main()
    cli_module.main()
    assert called["ok"] is True


def test_skeleton_help_lists_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "skeleton" in result.output


def test_skeleton_cli_runs_gamma_flow(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "skeleton",
            "--candidate-fixture",
            str(FIXTURES / "gamma-flow.yaml"),
            "--axiom",
            "predictors assume stationary return signal",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "rejected" in result.output
    assert "viability=0" in result.output
    assert "archive_empty" in result.output


def test_skeleton_cli_reports_non_mapping_yaml_concisely(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = tmp_path / "candidate.yaml"
    fixture.write_text("- item\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "skeleton",
            "--candidate-fixture",
            str(fixture),
            "--axiom",
            "predictors assume stationary return signal",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert result.stderr == "error: candidate fixture must be a mapping\n"


def test_skeleton_cli_reports_startup_errors_concisely(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    def boom(**_: object) -> None:
        raise OSError("adapter startup failed")

    monkeypatch.setattr(cli_module, "run_skeleton", boom)
    result = runner.invoke(
        app,
        [
            "skeleton",
            "--candidate-fixture",
            str(FIXTURES / "gamma-flow.yaml"),
            "--axiom",
            "predictors assume stationary return signal",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert result.stderr == "error: adapter startup failed\n"
