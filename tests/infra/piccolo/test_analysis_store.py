from __future__ import annotations

from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloAnalysisRunStore, PiccoloJobQueue


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
