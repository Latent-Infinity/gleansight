from __future__ import annotations

from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloAnalysisRunStore, PiccoloJobQueue


def test_list_runs_returns_all_runs_for_paper(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "runs.sqlite")
    db.initialize_schema()
    runs = PiccoloAnalysisRunStore()
    jobs = PiccoloJobQueue()

    # Create multiple runs for the same paper
    runs.create_run("run-1", "paper-a", "prompt", "profile", "model")
    job1 = jobs.enqueue("analyze", "paper-a", "run-1", {})
    jobs.mark_succeeded(job1)

    runs.create_run("run-2", "paper-a", "prompt", "profile", "model")
    job2 = jobs.enqueue("analyze", "paper-a", "run-2", {})
    jobs.mark_failed(job2, "test error")

    runs.create_run("run-3", "paper-a", "prompt", "profile", "model")
    job3 = jobs.enqueue("analyze", "paper-a", "run-3", {})
    # job3 is still queued

    # Create a run for a different paper
    runs.create_run("run-other", "paper-b", "prompt", "profile", "model")
    jobs.enqueue("analyze", "paper-b", "run-other", {})

    result = runs.list_runs("paper-a")

    assert len(result) == 3
    run_ids = {r["run_id"] for r in result}
    assert run_ids == {"run-1", "run-2", "run-3"}

    # Check status is included
    status_by_id = {r["run_id"]: r["status"] for r in result}
    assert status_by_id["run-1"] == "succeeded"
    assert status_by_id["run-2"] == "failed"
    assert status_by_id["run-3"] == "queued"


def test_list_runs_empty_for_unknown_paper(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "runs.sqlite")
    db.initialize_schema()
    runs = PiccoloAnalysisRunStore()

    result = runs.list_runs("nonexistent-paper")
    assert result == []


def test_latest_successful_run(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "runs.sqlite")
    db.initialize_schema()
    runs = PiccoloAnalysisRunStore()
    jobs = PiccoloJobQueue()

    run_id = "run-1"
    runs.create_run(run_id, "paper", "prompt", "profile", "model")
    job_id = jobs.enqueue("analyze", "paper", run_id, {})
    jobs.mark_succeeded(job_id)

    latest = runs.get_latest_successful_run(
        paper_id="paper",
        prompt_version_id="prompt",
        profile_id="profile",
        model_name="model",
    )
    assert latest is not None
    assert latest["run_id"] == run_id
