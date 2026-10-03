from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.profiles import llm_profile
from gleansight.api.runtime import ApiRuntime
from papers.app.ideation_contracts import PlanIdeaRequest
from papers.app.use_cases.idea_reviews import IdeaReviewService
from papers.app.use_cases.idea_reviews.planning import plan_reviewed_idea
from papers.app.use_cases.ideation import PlanIdeaUseCase
from papers.domain.idea_reviews import IdeaBinding, ReviewInput, Verdict
from papers.infra.idea_reviews import IdeaReviewStore


class BundleQuery(Request):
    project_id: Identifier | None = None


class BundlePath(Request):
    bundle_path: Path


class ReviewQuery(BundleQuery):
    bundle_path: Path | None = None


class RecordReview(Request):
    binding: IdeaBinding
    reviewer: Identifier
    verdict: Verdict
    rationale: Identifier
    previous_review_id: Identifier | None = None


class PlanReview(Request):
    review_id: Identifier
    selection_note: Identifier
    profile_id: Identifier | None = None
    model: Identifier | None = None
    timeout_s: Annotated[int, Field(ge=1, le=600)] = 300
    max_tokens: Annotated[int, Field(ge=256)] = 8000


def review_service(runtime: ApiRuntime) -> IdeaReviewService:
    return IdeaReviewService(IdeaReviewStore(runtime.paper_database), runtime.repo_root)


def bundles(runtime: ApiRuntime, request: BundleQuery) -> JsonValue:
    return json_result(
        {
            "bundles": [
                item.model_dump(mode="json")
                for item in review_service(runtime).bundles(request.project_id)
            ]
        }
    )


def inspect(runtime: ApiRuntime, request: BundlePath) -> JsonValue:
    return json_result(review_service(runtime).inspect(request.bundle_path).model_dump(mode="json"))


def record(runtime: ApiRuntime, request: RecordReview) -> JsonValue:
    result = review_service(runtime).record(ReviewInput.model_validate(request.model_dump()))
    return json_result(result.model_dump(mode="json"))


def history(runtime: ApiRuntime, request: ReviewQuery) -> JsonValue:
    service = review_service(runtime)
    path = (
        service.resolve_bundle(request.bundle_path).relative_to(runtime.repo_root)
        if request.bundle_path is not None
        else None
    )
    return json_result(
        {
            "reviews": [
                review.model_dump(mode="json")
                for review in service.store.history(path, request.project_id)
            ]
        }
    )


def plan(runtime: ApiRuntime, request: PlanReview) -> JsonValue:
    service = review_service(runtime)
    review = service.store.get(request.review_id)
    result = plan_reviewed_idea(
        service,
        request.review_id,
        PlanIdeaRequest(
            bundle=service.resolve_bundle(review.binding.bundle_path),
            idea_id=review.binding.idea_id,
            profile=llm_profile(runtime, request.profile_id),
            model=request.model or runtime.settings.llm.default_model,
            timeout_s=request.timeout_s,
            max_tokens=request.max_tokens,
            selection_note=request.selection_note,
        ),
        PlanIdeaUseCase(runtime.papers.llm_client, runtime.repo_root),
    )
    return json_result(result.model_dump(mode="json"))


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.reviews.bundles",
            "Browse generated, reviewed, and selected idea bundles.",
            BundleQuery,
            bundles,
        ),
        Operation(
            "papers.reviews.inspect",
            "Inspect frozen ideas, evidence, critique and review history.",
            BundlePath,
            inspect,
        ),
        Operation(
            "papers.reviews.record",
            "Record an attributed non-authorizing researcher decision.",
            RecordReview,
            record,
            ("write",),
        ),
        Operation(
            "papers.reviews.list",
            "Read immutable researcher decision history.",
            ReviewQuery,
            history,
        ),
        Operation(
            "papers.reviews.plan",
            "Plan the latest kept idea with a review-bound handoff.",
            PlanReview,
            plan,
            ("write", "external"),
        ),
    )
