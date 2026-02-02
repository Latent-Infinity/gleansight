from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from papers.app.use_cases.analysis import AnalyzeProjectUseCase, ReanalyzeWithPromptVersionUseCase
from papers.domain.errors import NotFoundError


@dataclass
class FakePromptStore:
    versions: dict[str, dict[str, str]]

    def get_version(self, prompt_version_id: str):
        return self.versions.get(prompt_version_id)


@dataclass
class FakePaperProjectStore:
    project_papers: dict[str, list[str]]
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    def list_paper_ids(self, project_id: str, label: str | None = None) -> list[str]:
        self.calls.append((project_id, label))
        return self.project_papers.get(project_id, [])


@dataclass
class FakeRunAnalysis:
    calls: list[dict[str, str | bool]] = field(default_factory=list)

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
                "prompt_version_id": prompt_version_id,
                "profile_id": profile_id,
                "model_name": model_name,
                "force": force,
            }
        )
        return f"run-{paper_id}"


def test_reanalyze_with_prompt_version_runs_scope() -> None:
    prompt_store = FakePromptStore({"pv1": {"prompt_id": "prompt", "prompt_version_id": "pv1"}})
    runner = FakeRunAnalysis()
    use_case = ReanalyzeWithPromptVersionUseCase(prompt_store=prompt_store, run_analysis=runner)

    runs = use_case(
        scope=["paper-1", "paper-2"],
        prompt_version_id="pv1",
        profile_id="profile",
        model_name="model",
        force=True,
    )

    assert runs == ["run-paper-1", "run-paper-2"]
    assert runner.calls == [
        {
            "paper_id": "paper-1",
            "prompt_id": "prompt",
            "prompt_version_id": "pv1",
            "profile_id": "profile",
            "model_name": "model",
            "force": True,
        },
        {
            "paper_id": "paper-2",
            "prompt_id": "prompt",
            "prompt_version_id": "pv1",
            "profile_id": "profile",
            "model_name": "model",
            "force": True,
        },
    ]


def test_reanalyze_requires_prompt_version() -> None:
    prompt_store = FakePromptStore({})
    runner = FakeRunAnalysis()
    use_case = ReanalyzeWithPromptVersionUseCase(prompt_store=prompt_store, run_analysis=runner)

    with pytest.raises(NotFoundError):
        use_case(
            scope=["paper-1"],
            prompt_version_id="missing",
            profile_id="profile",
            model_name="model",
        )


def test_analyze_project_uses_project_scope() -> None:
    prompt_store = FakePromptStore({"pv1": {"prompt_id": "prompt", "prompt_version_id": "pv1"}})
    project_store = FakePaperProjectStore({"project-1": ["paper-1"]})
    runner = FakeRunAnalysis()

    use_case = AnalyzeProjectUseCase(
        paper_project_store=project_store,
        prompt_store=prompt_store,
        run_analysis=runner,
    )

    runs = use_case(
        project_id="project-1",
        prompt_version_id="pv1",
        profile_id="profile",
        model_name="model",
        label="primary",
    )

    assert runs == ["run-paper-1"]
    assert project_store.calls == [("project-1", "primary")]
    assert runner.calls[0]["paper_id"] == "paper-1"


def test_analyze_project_returns_empty_when_no_papers() -> None:
    prompt_store = FakePromptStore({"pv1": {"prompt_id": "prompt", "prompt_version_id": "pv1"}})
    project_store = FakePaperProjectStore({})
    runner = FakeRunAnalysis()

    use_case = AnalyzeProjectUseCase(
        paper_project_store=project_store,
        prompt_store=prompt_store,
        run_analysis=runner,
    )

    runs = use_case(
        project_id="project-1",
        prompt_version_id="pv1",
        profile_id="profile",
        model_name="model",
    )

    assert runs == []
    assert runner.calls == []
