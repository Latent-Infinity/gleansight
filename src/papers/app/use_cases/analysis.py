from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from papers.app import ports
from papers.domain.errors import NotFoundError


@dataclass(frozen=True)
class ReanalyzeWithPromptVersionUseCase:
    prompt_store: ports.PromptStore
    run_analysis: Callable[..., str]

    def __call__(
        self,
        *,
        scope: list[str],
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
        force: bool = False,
    ) -> list[str]:
        version = self.prompt_store.get_version(prompt_version_id)
        if version is None:
            raise NotFoundError("prompt version not found")
        prompt_id = version["prompt_id"]
        run_ids: list[str] = []
        for paper_id in scope:
            run_ids.append(
                self.run_analysis(
                    paper_id=paper_id,
                    prompt_id=prompt_id,
                    prompt_version_id=prompt_version_id,
                    profile_id=profile_id,
                    model_name=model_name,
                    force=force,
                )
            )
        return run_ids


@dataclass(frozen=True)
class AnalyzeProjectUseCase:
    paper_project_store: ports.PaperProjectStore
    prompt_store: ports.PromptStore
    run_analysis: Callable[..., str]

    def __call__(
        self,
        *,
        project_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
        label: str | None = None,
        force: bool = False,
    ) -> list[str]:
        paper_ids = self.paper_project_store.list_paper_ids(project_id, label=label)
        if not paper_ids:
            return []
        version = self.prompt_store.get_version(prompt_version_id)
        if version is None:
            raise NotFoundError("prompt version not found")
        prompt_id = version["prompt_id"]
        return [
            self.run_analysis(
                paper_id=paper_id,
                prompt_id=prompt_id,
                prompt_version_id=prompt_version_id,
                profile_id=profile_id,
                model_name=model_name,
                force=force,
            )
            for paper_id in paper_ids
        ]
