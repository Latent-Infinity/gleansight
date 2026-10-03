from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypedDict

from pydantic import BaseModel, JsonValue, TypeAdapter

from papers.app.composition_root import AppContainer
from papers.app.ideation_contracts import LLMProfile, PlanIdeaRequest
from papers.app.use_cases.idea_reviews import IdeaReviewService
from papers.app.use_cases.idea_reviews.planning import plan_reviewed_idea
from papers.app.use_cases.ideation import PlanIdeaUseCase
from papers.domain.idea_reviews import IdeaReviewError, ReviewInput
from papers.infra.idea_reviews import IdeaReviewStore


class ListIdeaBundles(Protocol):
    def __call__(self, *, project_id: str | None = None) -> dict[str, JsonValue]: ...


class InspectIdeaReviews(Protocol):
    def __call__(self, *, bundle_path: str) -> dict[str, JsonValue]: ...


class RecordIdeaReview(Protocol):
    def __call__(
        self,
        *,
        binding: dict[str, JsonValue],
        reviewer: str,
        verdict: str,
        rationale: str,
        previous_review_id: str | None,
    ) -> dict[str, JsonValue]: ...


class PlanReviewedIdea(Protocol):
    def __call__(
        self,
        *,
        review_id: str,
        profile_id: str | None,
        model: str | None,
        timeout_s: int,
        max_tokens: int,
        selection_note: str,
    ) -> dict[str, JsonValue]: ...


class ReviewCallbacks(TypedDict):
    list_idea_bundles: ListIdeaBundles
    review_ideas: InspectIdeaReviews
    record_idea_review: RecordIdeaReview
    plan_reviewed_idea: PlanReviewedIdea


def _json(value: BaseModel) -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_python(value.model_dump(mode="json"))


def build_review_services(base: AppContainer, *, repo_root: Path) -> ReviewCallbacks:
    service = IdeaReviewService(IdeaReviewStore(base.db), repo_root.resolve())

    def bundles(*, project_id: str | None = None) -> dict[str, JsonValue]:
        return {"bundles": [_json(item) for item in service.bundles(project_id)]}

    def inspect(*, bundle_path: str) -> dict[str, JsonValue]:
        return _json(service.inspect(Path(bundle_path)))

    def record(
        *,
        binding: dict[str, JsonValue],
        reviewer: str,
        verdict: str,
        rationale: str,
        previous_review_id: str | None,
    ) -> dict[str, JsonValue]:
        request = ReviewInput.model_validate(
            {
                "binding": binding,
                "reviewer": reviewer,
                "verdict": verdict,
                "rationale": rationale,
                "previous_review_id": previous_review_id,
            }
        )
        return _json(service.record(request))

    def plan(
        *,
        review_id: str,
        profile_id: str | None,
        model: str | None,
        timeout_s: int,
        max_tokens: int,
        selection_note: str,
    ) -> dict[str, JsonValue]:
        stored = base.profile_store.get(profile_id or base.settings.llm.default_profile)
        if stored is None:
            raise IdeaReviewError("Configured LLM profile does not exist")
        keys = (
            "api_key",
            "base_url",
            "chat_options",
            "executable_path",
            "profile_id",
            "provider",
            "reasoning_effort",
        )
        profile = TypeAdapter(LLMProfile).validate_python(
            {key: value for key, value in stored.items() if key in keys}
        )
        review = service.store.get(review_id)
        result = plan_reviewed_idea(
            service,
            review_id,
            PlanIdeaRequest(
                bundle=service.resolve_bundle(review.binding.bundle_path),
                idea_id=review.binding.idea_id,
                profile=profile,
                model=model or base.settings.llm.default_model,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
                selection_note=selection_note,
            ),
            PlanIdeaUseCase(base.llm_client, repo_root),
        )
        return _json(result)

    return {
        "list_idea_bundles": bundles,
        "review_ideas": inspect,
        "record_idea_review": record,
        "plan_reviewed_idea": plan,
    }
