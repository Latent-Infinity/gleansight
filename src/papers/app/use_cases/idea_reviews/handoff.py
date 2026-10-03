from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import TypeAdapter

from papers.domain.idea_reviews import IdeaReview, IdeaReviewError, ReviewSelection, model_sha256
from papers.domain.ideation_bundle import BundleType, read_verified_text, verify_manifest


def verify_selection_artifacts(
    selection: ReviewSelection, review: IdeaReview, repo_root: Path
) -> None:
    if model_sha256(review) != selection.review_sha256 or review.binding != selection.binding:
        raise IdeaReviewError("Selected review identity changed")
    plan = (repo_root / selection.plan_bundle).resolve()
    handoff = (repo_root / selection.handoff_bundle).resolve()
    if any(not path.is_relative_to((repo_root / "output").resolve()) for path in (plan, handoff)):
        raise IdeaReviewError("Selection artifacts must remain under workspace output/")
    verify_manifest(plan, BundleType.selected_idea_plan)
    digest = hashlib.sha256(read_verified_text(plan / "manifest.json").encode()).hexdigest()
    if digest != selection.plan_manifest_sha256:
        raise IdeaReviewError("Selected plan changed")
    hashes = TypeAdapter(dict[str, str]).validate_json(
        read_verified_text(handoff / "manifest.json")
    )
    if set(hashes) != {"handoff.json"} or {path.name for path in handoff.iterdir()} != {
        "handoff.json",
        "manifest.json",
    }:
        raise IdeaReviewError("Review handoff has an invalid artifact set")
    recorded = ReviewSelection.model_validate_json(
        read_verified_text(handoff / "handoff.json", hashes["handoff.json"])
    )
    if recorded != selection:
        raise IdeaReviewError("Review handoff identity changed")
