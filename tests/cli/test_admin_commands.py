from __future__ import annotations

import importlib
from dataclasses import dataclass

from typer.testing import CliRunner


@dataclass
class FakeRecover:
    def __call__(self):
        return ["job-1", "job-2"]


@dataclass
class FakeRebuild:
    def __call__(self):
        return 3


@dataclass
class FakeContainer:
    recover_jobs: FakeRecover
    rebuild_index: FakeRebuild
    rebuild_fts: FakeRebuild


def test_recover_jobs_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        recover_jobs=FakeRecover(),
        rebuild_index=FakeRebuild(),
        rebuild_fts=FakeRebuild(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["recover-jobs"])

    assert result.exit_code == 0
    assert "Recovered 2 jobs" in result.output


def test_rebuild_index_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        recover_jobs=FakeRecover(),
        rebuild_index=FakeRebuild(),
        rebuild_fts=FakeRebuild(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["rebuild-index"])

    assert result.exit_code == 0
    assert "Rebuilt vector index for 3 papers" in result.output


def test_rebuild_fts_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        recover_jobs=FakeRecover(),
        rebuild_index=FakeRebuild(),
        rebuild_fts=FakeRebuild(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["rebuild-fts"])

    assert result.exit_code == 0
    assert "Rebuilt title/abstract index for 3 papers" in result.output
