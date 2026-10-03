from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from papers.app.use_cases.idea_reviews.handoff import verify_selection_artifacts
from papers.domain.idea_reviews import (
    IdeaBinding,
    IdeaReview,
    IdeaReviewError,
    ReviewBundleSummary,
    ReviewDesk,
    ReviewedIdea,
    ReviewInput,
    model_sha256,
)
from papers.domain.ideation import Critique
from papers.domain.ideation_bundle import (
    BundleIntegrityError,
    BundleType,
    read_verified_text,
    verify_manifest,
)
from papers.domain.ideation_frozen import load_frozen_ideation_inputs
from papers.infra.idea_reviews import IdeaReviewStore


@dataclass(frozen=True, slots=True)
class IdeaReviewService:
    store: IdeaReviewStore
    repo_root: Path

    def resolve_bundle(self, path: Path) -> Path:
        requested = path if path.is_absolute() else self.repo_root / path
        resolved = requested.resolve()
        if requested.is_symlink() or not resolved.is_relative_to(
            (self.repo_root / "output").resolve()
        ):
            raise IdeaReviewError("Ideation bundle must be a regular directory under output/")
        return resolved

    def inspect(self, path: Path) -> ReviewDesk:
        bundle = self.resolve_bundle(path)
        hashes = verify_manifest(bundle, BundleType.project_ideation)
        evidence, generation = load_frozen_ideation_inputs(bundle, hashes)
        critique = Critique.model_validate_json(
            read_verified_text(bundle / "critique.json", hashes["critique.json"])
        )
        digest = hashlib.sha256(read_verified_text(bundle / "manifest.json").encode()).hexdigest()
        history = self.store.history(bundle.relative_to(self.repo_root.resolve()))
        selections = self.store.selections()
        ideas: list[ReviewedIdea] = []
        for idea in generation.ideas:
            binding = IdeaBinding(
                bundle_path=bundle.relative_to(self.repo_root.resolve()),
                bundle_sha256=digest,
                project_id=evidence.project_id,
                idea_id=idea.idea_id,
                idea_sha256=model_sha256(idea),
            )
            reviews = tuple(review for review in history if review.binding.idea_id == idea.idea_id)
            current = tuple(review for review in reviews if review.binding == binding)
            selected = tuple(selection for selection in selections if selection.binding == binding)
            for selection in selected:
                verify_selection_artifacts(
                    selection, self.store.get(selection.review_id), self.repo_root
                )
            state = "generated"
            if current:
                state = "reviewed"
                if current[-1].verdict == "keep" and any(
                    s.review_id == current[-1].review_id for s in selected
                ):
                    state = "selected"
            ideas.append(
                ReviewedIdea(
                    idea=idea,
                    binding=binding,
                    critique=next(
                        item for item in critique.reviews if item.idea_id == idea.idea_id
                    ),
                    evidence=tuple(
                        item
                        for item in evidence.excerpts
                        if item.excerpt_id in idea.citation_excerpt_ids
                    ),
                    reviews=reviews,
                    selections=selected,
                    state=state,
                    stale_review_ids=tuple(
                        review.review_id for review in reviews if review.binding != binding
                    ),
                )
            )
        return ReviewDesk(
            bundle_path=bundle,
            project_id=evidence.project_id,
            question=generation.question,
            ideas=tuple(ideas),
        )

    def require_binding(self, binding: IdeaBinding) -> ReviewedIdea:
        for idea in self.inspect(binding.bundle_path).ideas:
            if idea.binding == binding:
                return idea
        raise IdeaReviewError("The bundle or idea changed; reload before reviewing or planning")

    def record(self, request: ReviewInput) -> IdeaReview:
        self.require_binding(request.binding)
        return self.store.append(request)

    def bundles(self, project_id: str | None = None) -> tuple[ReviewBundleSummary, ...]:
        result: list[ReviewBundleSummary] = []
        for path in sorted((self.repo_root / "output/project-ideation").glob("*"), reverse=True):
            if path.name.startswith("."):
                continue
            try:
                desk = self.inspect(path)
                if project_id is not None and desk.project_id != project_id:
                    continue
                states = {idea.state for idea in desk.ideas}
                state = (
                    "selected"
                    if "selected" in states
                    else "reviewed"
                    if "reviewed" in states
                    else "generated"
                )
                result.append(
                    ReviewBundleSummary(
                        bundle_path=path, project_id=desk.project_id, state=state, problem=None
                    )
                )
            except (BundleIntegrityError, IdeaReviewError) as exc:
                result.append(
                    ReviewBundleSummary(
                        bundle_path=path, project_id=None, state="invalid", problem=str(exc)
                    )
                )
        return tuple(result)
