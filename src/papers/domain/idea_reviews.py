from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from papers.domain.ideation import DraftIdea, EvidenceExcerpt, IdeaCritique
from papers.domain.investigation_evidence import ContractModel, NonEmptyStr

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Verdict = Literal["keep", "revise", "reject"]


@dataclass(frozen=True, slots=True)
class IdeaReviewError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class IdeaBinding(ContractModel):
    bundle_path: Path
    bundle_sha256: Sha256
    project_id: NonEmptyStr
    idea_id: NonEmptyStr
    idea_sha256: Sha256


class ReviewInput(ContractModel):
    binding: IdeaBinding
    reviewer: NonEmptyStr
    verdict: Verdict
    rationale: NonEmptyStr
    previous_review_id: NonEmptyStr | None


class IdeaReview(ReviewInput):
    review_id: NonEmptyStr
    revision: int = Field(ge=1)
    created_at: NonEmptyStr
    grants_nsqd_approval: Literal[False] = False
    verifies_evidence: Literal[False] = False


class ReviewSelection(ContractModel):
    selection_id: NonEmptyStr
    review_id: NonEmptyStr
    review_sha256: Sha256
    binding: IdeaBinding
    created_at: NonEmptyStr
    plan_bundle: Path
    plan_manifest_sha256: Sha256
    handoff_bundle: Path
    selection_note: NonEmptyStr
    grants_nsqd_approval: Literal[False] = False
    verifies_evidence: Literal[False] = False
    activates_operator: Literal[False] = False


class ReviewedIdea(ContractModel):
    idea: DraftIdea
    binding: IdeaBinding
    critique: IdeaCritique
    evidence: tuple[EvidenceExcerpt, ...]
    reviews: tuple[IdeaReview, ...]
    selections: tuple[ReviewSelection, ...]
    state: Literal["generated", "reviewed", "selected"]
    stale_review_ids: tuple[str, ...]


class ReviewDesk(ContractModel):
    bundle_path: Path
    project_id: NonEmptyStr
    question: NonEmptyStr
    ideas: tuple[ReviewedIdea, ...]


class ReviewBundleSummary(ContractModel):
    bundle_path: Path
    project_id: str | None
    state: Literal["generated", "reviewed", "selected", "invalid"]
    problem: str | None


def model_sha256(value: BaseModel) -> str:
    raw = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
