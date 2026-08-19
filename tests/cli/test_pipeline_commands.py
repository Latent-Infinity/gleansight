from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import datetime

from typer.testing import CliRunner


@dataclass
class FakeJobRunner:
    calls: list[datetime] = field(default_factory=list)

    def run_next(self, now: datetime) -> bool:
        self.calls.append(now)
        return len(self.calls) == 1


@dataclass
class FakeRunAnalysis:
    calls: list[dict[str, str]] = field(default_factory=list)

    def __call__(
        self,
        *,
        paper_id: str,
        prompt_id: str,
        prompt_version_id: str | None,
        profile_id: str,
        model_name: str,
        force: bool = False,
    ) -> str:
        self.calls.append(
            {
                "paper_id": paper_id,
                "prompt_id": prompt_id,
                "prompt_version_id": prompt_version_id or "",
                "profile_id": profile_id,
                "model_name": model_name,
                "force": str(force),
            }
        )
        return "run-1"


@dataclass
class FakeJobQueue:
    def list_jobs(self, limit: int = 50):
        return [
            {"status": "queued"},
            {"status": "succeeded"},
            {"status": "queued"},
        ]


@dataclass
class FakeContainer:
    job_runner: FakeJobRunner
    run_analysis: FakeRunAnalysis
    job_queue: FakeJobQueue


def test_run_jobs(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        job_runner=FakeJobRunner(),
        run_analysis=FakeRunAnalysis(),
        job_queue=FakeJobQueue(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["run-jobs", "--max-jobs", "3"])

    assert result.exit_code == 0
    assert "Processed 1 jobs" in result.output


def test_analyze_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        job_runner=FakeJobRunner(),
        run_analysis=FakeRunAnalysis(),
        job_queue=FakeJobQueue(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "analyze",
            "paper-1",
            "--prompt-id",
            "prompt",
            "--profile-id",
            "profile",
            "--model-name",
            "model",
        ],
    )

    assert result.exit_code == 0
    assert "run-1" in result.output
    assert container.run_analysis.calls[0]["paper_id"] == "paper-1"


def test_status_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        job_runner=FakeJobRunner(),
        run_analysis=FakeRunAnalysis(),
        job_queue=FakeJobQueue(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["status"])

    assert result.exit_code == 0
    assert "queued" in result.output
    assert "succeeded" in result.output


def test_run_jobs_daemon_mode(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()

    @dataclass
    class DaemonJobRunner:
        calls: list[datetime] = field(default_factory=list)

        def run_next(self, now: datetime) -> bool:
            self.calls.append(now)
            return len(self.calls) <= 2

    @dataclass
    class DaemonContainer:
        job_runner: DaemonJobRunner
        run_analysis: FakeRunAnalysis
        job_queue: FakeJobQueue

    container = DaemonContainer(
        job_runner=DaemonJobRunner(),
        run_analysis=FakeRunAnalysis(),
        job_queue=FakeJobQueue(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        ["run-jobs", "--daemon", "--max-iterations", "3", "--poll-interval", "0.001"],
    )

    assert result.exit_code == 0
    assert len(container.job_runner.calls) == 3


def test_status_command_when_list_jobs_unavailable(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()

    @dataclass
    class QueueWithoutListJobs:
        pass

    @dataclass
    class StatusContainer:
        job_runner: FakeJobRunner
        run_analysis: FakeRunAnalysis
        job_queue: QueueWithoutListJobs

    container = StatusContainer(
        job_runner=FakeJobRunner(),
        run_analysis=FakeRunAnalysis(),
        job_queue=QueueWithoutListJobs(),
    )
    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["status"])

    assert result.exit_code == 1
    assert "Job status unavailable" in result.output
