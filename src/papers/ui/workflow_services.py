from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from nsqd.app.use_cases import MapSnapshotUseCase, RankArchiveUseCase
from nsqd.composition import NsqdContainer
from nsqd.domain.coverage import RankGuardBlocked
from papers.app.composition_root import AppContainer
from papers.app.ideation_contracts import IdeateProjectRequest, LLMProfile, PlanIdeaRequest
from papers.app.use_cases import IdeateProjectUseCase, PlanIdeaUseCase
from papers.ui.path_policy import resolve_report_bundle

_PROFILE_KEYS = frozenset(
    {
        "api_key",
        "base_url",
        "chat_options",
        "executable_path",
        "profile_id",
        "provider",
        "reasoning_effort",
    }
)
_PROFILE_ADAPTER = TypeAdapter(LLMProfile)
type WorkflowCallback = Callable[..., dict[str, Any]]


def build_ideation_callbacks(
    base: AppContainer, *, repo_root: Path
) -> tuple[WorkflowCallback, WorkflowCallback]:
    ideate_use_case = IdeateProjectUseCase(
        project_store=base.project_store,
        paper_project_store=base.paper_project_store,
        paper_store=base.paper_store,
        blob_store=base.blob_store,
        llm_client=base.llm_client,
        repo_root=repo_root,
    )
    plan_use_case = PlanIdeaUseCase(llm_client=base.llm_client, repo_root=repo_root)

    def profile(profile_id: str | None) -> LLMProfile:
        resolved_id = profile_id or base.settings.llm.default_profile
        stored = base.profile_store.get(resolved_id)
        if stored is None:
            raise ValueError(f"profile not found: {resolved_id}")
        return _PROFILE_ADAPTER.validate_python(
            {key: value for key, value in stored.items() if key in _PROFILE_KEYS}
        )

    def ideate_project(
        *,
        project_id: str,
        question: str,
        profile_id: str | None,
        model: str | None,
        critic_model: str | None,
        max_papers: int,
        excerpt_bytes: int,
        max_excerpts_per_paper: int,
        timeout_s: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        bundle = ideate_use_case.run(
            IdeateProjectRequest(
                project_id=project_id,
                question=question,
                profile=profile(profile_id),
                model=model or base.settings.llm.default_model,
                critic_model=critic_model,
                max_papers=max_papers,
                excerpt_bytes=excerpt_bytes,
                max_excerpts_per_paper=max_excerpts_per_paper,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
            )
        )
        return {"bundle": str(bundle)}

    def plan_idea(
        *,
        bundle_path: str,
        idea_id: str,
        profile_id: str | None,
        model: str | None,
        timeout_s: int,
        max_tokens: int,
        selection_note: str,
    ) -> dict[str, Any]:
        bundle = resolve_report_bundle(bundle_path, repo_root=repo_root, field="bundle_path")
        plan_bundle = plan_use_case.run(
            PlanIdeaRequest(
                bundle=bundle,
                idea_id=idea_id,
                profile=profile(profile_id),
                model=model or base.settings.llm.default_model,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
                selection_note=selection_note,
            )
        )
        return {"bundle": str(plan_bundle)}

    return ideate_project, plan_idea


def build_rank_callback(nsqd: NsqdContainer) -> WorkflowCallback:
    def rank_archive(
        *, snapshot_id: str, domain_policy_id: str, snapshot_state: str
    ) -> dict[str, Any]:
        mapped = MapSnapshotUseCase(
            snapshots=nsqd.ctx.snapshots,
            records=nsqd.ctx.records,
            morph=nsqd.ctx.morph,
            clock=nsqd.clock,
        ).run(
            snapshot_id=snapshot_id,
            domain_policy_id=domain_policy_id,
            snapshot_state=snapshot_state,
        )
        policy_elites = [
            card
            for card in nsqd.ctx.cards.list_elites()
            if str(card.get("domain_policy_id") or "") == domain_policy_id
        ]
        try:
            rank = RankArchiveUseCase(
                cell_statuses=mapped["cell_statuses"],
                domain_policy_id=domain_policy_id,
            ).run(elite_cell_ids={str(card["cell_id"]) for card in policy_elites})
        except RankGuardBlocked as exc:
            rank = {"allowed": False, "reason": str(exc)}
        return {
            "snapshot_id": snapshot_id,
            "domain_policy_id": domain_policy_id,
            "elites": len(policy_elites),
            "rank": rank,
        }

    return rank_archive
