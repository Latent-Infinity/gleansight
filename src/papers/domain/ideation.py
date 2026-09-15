from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Self, assert_never

from pydantic import Field, model_validator

from papers.domain.investigation_evidence import (
    CompletionStr,
    ContractModel,
    ContractValueError,
    NonEmptyStr,
)


class EvidenceCategory(StrEnum):
    method = "method"
    data = "data"
    evaluation = "evaluation"
    limitations = "limitations"
    counterevidence = "counterevidence"
    future_work = "future_work"


class IdeationClaimKind(StrEnum):
    paper_claim = "paper_claim"
    inference = "inference"
    unknown = "unknown"


class CritiqueVerdict(StrEnum):
    keep = "keep"
    revise = "revise"
    reject = "reject"


class PaperInventory(ContractModel):
    paper_id: NonEmptyStr
    title: CompletionStr
    markdown_missing: bool
    partial: bool
    markdown_bytes: int = Field(ge=0)
    selected_bytes: int = Field(ge=0)
    selected_excerpt_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.markdown_missing and (self.markdown_bytes or self.selected_bytes):
            raise ContractValueError("missing markdown cannot report selected bytes")
        if self.selected_bytes > self.markdown_bytes:
            raise ContractValueError("selected bytes cannot exceed markdown bytes")
        if self.partial != (self.selected_bytes < self.markdown_bytes):
            raise ContractValueError("partial flag must reflect selected coverage")
        return self


class EvidenceExcerpt(ContractModel):
    excerpt_id: NonEmptyStr
    paper_id: NonEmptyStr
    title: CompletionStr
    section: CompletionStr
    byte_start: int = Field(ge=0)
    byte_end: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote: NonEmptyStr

    @model_validator(mode="after")
    def validate_bytes(self) -> Self:
        quote_bytes = self.quote.encode()
        if self.byte_end - self.byte_start != len(quote_bytes):
            raise ContractValueError("excerpt byte offsets do not match quote length")
        if hashlib.sha256(quote_bytes).hexdigest() != self.sha256:
            raise ContractValueError("excerpt hash does not match quote")
        return self


class EvidenceMap(ContractModel):
    project_id: NonEmptyStr
    project_name: CompletionStr
    inventory: tuple[PaperInventory, ...]
    excerpts: tuple[EvidenceExcerpt, ...]
    coverage_note: CompletionStr

    @model_validator(mode="after")
    def validate_inventory_closure(self) -> Self:
        inventory_ids = [paper.paper_id for paper in self.inventory]
        excerpt_ids = [excerpt.excerpt_id for excerpt in self.excerpts]
        if len(inventory_ids) != len(set(inventory_ids)):
            raise ContractValueError("inventory paper IDs must be unique")
        if len(excerpt_ids) != len(set(excerpt_ids)):
            raise ContractValueError("excerpt IDs must be unique")
        inventory = {paper.paper_id: paper for paper in self.inventory}
        selected_by_excerpt: dict[str, str] = {}
        for paper in self.inventory:
            for excerpt_id in paper.selected_excerpt_ids:
                if excerpt_id in selected_by_excerpt:
                    raise ContractValueError("inventory excerpt IDs must be unique")
                selected_by_excerpt[excerpt_id] = paper.paper_id
        if set(selected_by_excerpt) != set(excerpt_ids):
            raise ContractValueError("inventory must list exactly the evidence excerpts")
        for excerpt in self.excerpts:
            paper = inventory.get(excerpt.paper_id)
            if (
                paper is None
                or selected_by_excerpt[excerpt.excerpt_id] != excerpt.paper_id
                or excerpt.title != paper.title
            ):
                raise ContractValueError("evidence excerpt does not match inventory")
        return self


class EvidenceCard(ContractModel):
    card_id: NonEmptyStr
    category: EvidenceCategory
    claim_kind: IdeationClaimKind
    statement: CompletionStr | None
    excerpt_ids: tuple[NonEmptyStr, ...]
    uncertainty: CompletionStr | None

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        match self.claim_kind:
            case IdeationClaimKind.paper_claim:
                if self.statement is None or not self.excerpt_ids:
                    raise ContractValueError("paper claims require a statement and excerpts")
            case IdeationClaimKind.inference:
                if self.statement is None or (not self.excerpt_ids and self.uncertainty is None):
                    raise ContractValueError(
                        "inferences require a statement and support or uncertainty"
                    )
            case IdeationClaimKind.unknown:
                if self.uncertainty is None:
                    raise ContractValueError("unknown cards require uncertainty")
            case unreachable:
                assert_never(unreachable)
        return self


class DraftIdea(ContractModel):
    idea_id: NonEmptyStr
    title: CompletionStr
    gap: CompletionStr
    mechanism: CompletionStr
    citation_excerpt_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    known_overlap: CompletionStr | None
    falsifiable_question: CompletionStr
    smallest_test: CompletionStr
    data_assumptions: CompletionStr | None
    model_assumptions: CompletionStr | None
    compute_assumptions: CompletionStr | None
    feasibility_uncertainty: CompletionStr


class GenerationOutput(ContractModel):
    question: NonEmptyStr
    evidence_cards: tuple[EvidenceCard, ...]
    ideas: tuple[DraftIdea, ...] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        card_ids = [card.card_id for card in self.evidence_cards]
        idea_ids = [idea.idea_id for idea in self.ideas]
        if len(card_ids) != len(set(card_ids)):
            raise ContractValueError("evidence card IDs must be unique")
        if len(idea_ids) != len(set(idea_ids)):
            raise ContractValueError("idea IDs must be unique")
        return self


class IdeaCritique(ContractModel):
    idea_id: NonEmptyStr
    verdict: CritiqueVerdict
    rationale: CompletionStr
    overlap: CompletionStr | None
    contradiction: CompletionStr | None
    uncertainty: CompletionStr
    duplicate_of: NonEmptyStr | None
    evidence_excerpt_ids: tuple[NonEmptyStr, ...]


class Critique(ContractModel):
    reviews: tuple[IdeaCritique, ...]
