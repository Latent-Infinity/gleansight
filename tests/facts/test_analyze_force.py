from __future__ import annotations

from pathlib import Path

from papers.app.use_cases.pipeline import RunAnalysisUseCase
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloJobQueue,
    PiccoloProfileStore,
    PiccoloPromptStore,
)


def test_force_creates_new_run_and_leaves_prior(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "force.sqlite")
    db.initialize_schema()
    prompts = PiccoloPromptStore()
    profiles = PiccoloProfileStore()
    runs = PiccoloAnalysisRunStore()
    jobs = PiccoloJobQueue()
    prompts.create_prompt("prompt", "Prompt")
    prompts.create_version("pv1", "prompt", 1, "body", "markdown_only")
    profiles.create_profile("profile", "Local", "http://localhost")
    use_case = RunAnalysisUseCase(
        job_queue=jobs,
        prompt_store=prompts,
        profile_store=profiles,
        analysis_store=runs,
    )

    first = use_case(
        paper_id="paper",
        prompt_id="prompt",
        prompt_version_id="pv1",
        profile_id="profile",
        model_name="model",
        force=False,
    )
    job = next(row for row in jobs.list_jobs() if row["run_id"] == first)
    jobs.mark_succeeded(job["job_id"])

    reused = use_case(
        paper_id="paper",
        prompt_id="prompt",
        prompt_version_id="pv1",
        profile_id="profile",
        model_name="model",
        force=False,
    )
    forced = use_case(
        paper_id="paper",
        prompt_id="prompt",
        prompt_version_id="pv1",
        profile_id="profile",
        model_name="model",
        force=True,
    )

    listed = runs.list_runs("paper")
    listed_ids = {row["run_id"] for row in listed}
    analyze_jobs = [row for row in jobs.list_jobs() if row["type"] == "analyze"]
    assert reused == first
    assert forced != first
    assert first in listed_ids
    assert forced in listed_ids
    assert {row["run_id"] for row in analyze_jobs} == {first, forced}
    assert next(row for row in analyze_jobs if row["run_id"] == first)["status"] == "succeeded"
