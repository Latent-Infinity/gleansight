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
    assert "harvest" in result.output
    assert "project" in result.output
    assert "map" in result.output
    assert "diverge" in result.output
    assert "ground" in result.output
    assert "gate" in result.output
    assert "archive" in result.output


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


def test_project_cli_runs_approved_projection(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "--projection",
            str(FIXTURES / "paper-a.yaml"),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "projected" in result.output
    assert "created=True" in result.output


def test_project_cli_reports_manifest_rejection_concisely(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = tmp_path / "paper-a.yaml"
    fixture.write_text(
        (FIXTURES / "paper-a.yaml").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "project",
            "--projection",
            str(fixture),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
            "--db",
            str(tmp_path / "bad.sqlite"),
            "--index",
            str(tmp_path / "bad.lancedb"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "approved" in result.stderr or "content hash" in result.stderr


def test_map_and_archive_cli_on_empty_snapshot(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from nsqd.composition import build_container
    from nsqd.null_adapters import FixedClock

    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    container = build_container(
        db_path=db,
        index_path=index,
        clock=FixedClock(datetime(2024, 1, 1, tzinfo=UTC)),
    )
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1
    runner = CliRunner()
    mapped = runner.invoke(
        app,
        [
            "map",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--snapshot-state",
            "calibration",
            "--db",
            str(db),
            "--index",
            str(index),
        ],
    )
    assert mapped.exit_code == 0, mapped.output
    assert "Unknown" in mapped.output
    archived = runner.invoke(
        app,
        [
            "archive",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--db",
            str(db),
            "--index",
            str(index),
        ],
    )
    assert archived.exit_code == 0, archived.output
    assert "rank_guard_blocked" in archived.output


def test_diverge_ground_gate_cli_error_paths(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = tmp_path / "candidate.yaml"
    fixture.write_text("- item\n", encoding="utf-8")
    diverged = runner.invoke(
        app,
        [
            "diverge",
            "--candidate-fixture",
            str(fixture),
            "--axiom",
            "x",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert diverged.exit_code != 0
    ground = runner.invoke(
        app,
        [
            "ground",
            "--candidate-artifact-hash",
            "missing",
            "--snapshot-id",
            "snap",
            "--corpus-version",
            "1",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert ground.exit_code != 0
    gated = runner.invoke(
        app,
        [
            "gate",
            "--candidate-artifact-hash",
            "missing",
            "--snapshot-id",
            "snap",
            "--corpus-version",
            "1",
            "--evaluator-run-id",
            "eval-1",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert gated.exit_code != 0
