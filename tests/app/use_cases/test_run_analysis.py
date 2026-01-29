from __future__ import annotations

from pathlib import Path

from papers.app.use_cases import RunAnalysisUseCase
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloJobQueue,
    PiccoloProfileStore,
    PiccoloPromptStore,
)


def test_run_analysis_returns_existing_success(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()
    job_queue = PiccoloJobQueue()

    prompt_store.create_prompt("prompt", "Prompt")
    prompt_store.create_version("pv1", "prompt", 1, "body", "markdown_only")
    profile_store.create_profile("profile", "Local", "http://localhost")

    analysis_store.create_run("run", "paper", "pv1", "profile", "model")
    job_id = job_queue.enqueue("analyze", "paper", "run", {})
    job_queue.mark_succeeded(job_id)

    use_case = RunAnalysisUseCase(job_queue, prompt_store, profile_store, analysis_store)
    run_id = use_case(
        paper_id="paper",
        prompt_id="prompt",
        prompt_version_id=None,
        profile_id="profile",
        model_name="model",
        force=False,
    )
    assert run_id == "run"
