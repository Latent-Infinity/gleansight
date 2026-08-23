from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from gleansight.cli import app
from nsqd.composition import build_container
from nsqd.null_adapters import FixedClock


def test_gleansight_help_lists_discovery_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for name in ("harvest", "map", "diverge", "ground", "gate", "archive"):
        assert name in result.output


def test_gleansight_module_main_invokes_app(monkeypatch) -> None:
    import gleansight.__main__ as main_module
    import gleansight.cli as cli_module

    called = {"ok": False}

    def fake_app() -> None:
        called["ok"] = True

    monkeypatch.setattr(main_module, "app", fake_app)
    monkeypatch.setattr(cli_module, "app", fake_app)
    main_module.main()
    cli_module.main()
    assert called["ok"] is True


def test_gleansight_map_prints_status_counts(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    container = build_container(
        db_path=db,
        index_path=index,
        clock=FixedClock(datetime(2024, 1, 1, tzinfo=UTC)),
    )
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    result = CliRunner().invoke(
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
    assert result.exit_code == 0, result.output
    assert "snap" in result.output
    assert "finance/1" in result.output
    assert "Unknown" in result.output


def test_gleansight_harvest_still_rejects_essay(tmp_path: Path) -> None:
    essay = tmp_path / "survey.md"
    essay.write_text("This essay reviews convexity without listing a source.\n", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "harvest",
            "--file",
            str(essay),
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert result.exit_code != 0
    assert "rejected" in result.output.lower() or "error" in result.output.lower()


def test_gleansight_map_unknown_snapshot_fails(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "map",
            "--snapshot-id",
            "missing",
            "--domain-policy-id",
            "finance/1",
            "--snapshot-state",
            "calibration",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert result.exit_code != 0
    assert "error" in result.output.lower()


def test_gleansight_archive_reports_blocked_rank(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    container = build_container(
        db_path=db,
        index_path=index,
        clock=FixedClock(datetime(2024, 1, 1, tzinfo=UTC)),
    )
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    result = CliRunner().invoke(
        app,
        [
            "archive",
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
    assert result.exit_code == 0, result.output
    assert '"elites": 0' in result.output
    assert "rank_guard_blocked" in result.output


def test_gleansight_diverge_rejects_non_mapping_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "candidate.yaml"
    fixture.write_text("- item\n", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "diverge",
            "--candidate-fixture",
            str(fixture),
            "--axiom",
            "predictors assume stationary return signal",
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
    assert result.exit_code != 0
    assert "error" in result.output.lower()


def test_gleansight_ground_and_gate_unknown_artifact_fail(tmp_path: Path) -> None:
    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    shared = [
        "--candidate-artifact-hash",
        "missing",
        "--snapshot-id",
        "snap",
        "--corpus-version",
        "1",
        "--db",
        str(db),
        "--index",
        str(index),
    ]
    ground = CliRunner().invoke(app, ["ground", *shared])
    assert ground.exit_code != 0
    gate = CliRunner().invoke(
        app,
        ["gate", *shared, "--evaluator-run-id", "eval-1", "--snapshot-state", "calibration"],
    )
    assert gate.exit_code != 0
