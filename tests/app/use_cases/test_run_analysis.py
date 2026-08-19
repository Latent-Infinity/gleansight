from __future__ import annotations

from pathlib import Path

import pytest

from papers.app.use_cases import RunAnalysisUseCase
from papers.domain.errors import NotFoundError
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


def test_run_analysis_raises_when_profile_missing(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()
    job_queue = PiccoloJobQueue()

    prompt_store.create_prompt("prompt", "Prompt")
    prompt_store.create_version("pv1", "prompt", 1, "body", "markdown_only")

    use_case = RunAnalysisUseCase(job_queue, prompt_store, profile_store, analysis_store)
    with pytest.raises(NotFoundError, match="profile not found"):
        use_case(
            paper_id="paper",
            prompt_id="prompt",
            prompt_version_id="pv1",
            profile_id="missing-profile",
            model_name="model",
            force=False,
        )


def test_run_analysis_requires_prompt_version_to_match_prompt(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()
    job_queue = PiccoloJobQueue()

    prompt_store.create_prompt("prompt-a", "Prompt A")
    prompt_store.create_prompt("prompt-b", "Prompt B")
    prompt_store.create_version("pv-b1", "prompt-b", 1, "body", "markdown_only")
    profile_store.create_profile("profile", "Local", "http://localhost")

    use_case = RunAnalysisUseCase(job_queue, prompt_store, profile_store, analysis_store)
    with pytest.raises(NotFoundError, match="prompt version not found for prompt"):
        use_case(
            paper_id="paper",
            prompt_id="prompt-a",
            prompt_version_id="pv-b1",
            profile_id="profile",
            model_name="model",
            force=False,
        )
