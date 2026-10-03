from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from papers.app.ideation_contracts import PlanIdeaRequest
from papers.app.use_cases.idea_reviews.service import IdeaReviewService
from papers.app.use_cases.ideation import PlanIdeaUseCase
from papers.domain.idea_reviews import IdeaReview, IdeaReviewError, ReviewSelection, model_sha256
from papers.domain.ideation_bundle import (
    BundleType,
    atomic_bundle,
    read_verified_text,
    verify_manifest,
    write_json,
    write_manifest,
)


def require_current_keep(service: IdeaReviewService, review_id: str) -> IdeaReview:
    review = service.store.get(review_id)
    idea = service.require_binding(review.binding)
    if not idea.reviews or idea.reviews[-1].review_id != review_id:
        raise IdeaReviewError("Only the latest researcher decision can be selected")
    if review.verdict != "keep":
        raise IdeaReviewError("Planning requires a current keep decision")
    return review


def plan_reviewed_idea(
    service: IdeaReviewService, review_id: str, request: PlanIdeaRequest, planner: PlanIdeaUseCase
) -> ReviewSelection:
    review = require_current_keep(service, review_id)
    if (
        service.resolve_bundle(request.bundle) != service.resolve_bundle(review.binding.bundle_path)
        or request.idea_id != review.binding.idea_id
    ):
        raise IdeaReviewError("Planning request does not match the reviewed bundle and idea")
    plan = planner.run(request)
    require_current_keep(service, review_id)
    verify_manifest(plan, BundleType.selected_idea_plan)
    plan_digest = hashlib.sha256(read_verified_text(plan / "manifest.json").encode()).hexdigest()
    with atomic_bundle(service.repo_root, "idea-review-handoff") as (staging, published):
        selection = ReviewSelection(
            selection_id=uuid4().hex,
            review_id=review_id,
            review_sha256=model_sha256(review),
            binding=review.binding,
            created_at=datetime.now(UTC).isoformat(),
            plan_bundle=plan.relative_to(service.repo_root.resolve()),
            plan_manifest_sha256=plan_digest,
            handoff_bundle=published.relative_to(service.repo_root.resolve()),
            selection_note=request.selection_note,
        )
        write_json(staging / "handoff.json", selection.model_dump(mode="json"))
        write_manifest(staging, ("handoff.json",))
    # A concurrent reviewer revision cannot silently authorize this handoff.
    service.store.select(selection)
    return selection
