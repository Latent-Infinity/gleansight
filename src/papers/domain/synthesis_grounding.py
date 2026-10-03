from __future__ import annotations

import hashlib
from typing import Literal, Self

from pydantic import Field, model_validator

from papers.domain.ideation import EvidenceExcerpt
from papers.domain.ideation_evidence import _section_excerpts
from papers.domain.investigation_evidence import ContractModel, ContractValueError, NonEmptyStr


class GroundedSource(EvidenceExcerpt):
    markdown_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int | None = Field(ge=1)


class GroundedClaim(ContractModel):
    text: NonEmptyStr
    references: tuple[GroundedSource, ...] = Field(min_length=1)


class GroundedAnswer(ContractModel):
    status: Literal["supported", "insufficient", "conflicting"]
    claims: tuple[GroundedClaim, ...]
    limitations: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status != "insufficient" and not self.claims:
            raise ContractValueError("Supported or conflicting answers require cited claims")
        if self.status == "insufficient" and (self.claims or not self.limitations):
            raise ContractValueError("Insufficient answers require limitations and no claims")
        if self.status == "conflicting":
            papers = {ref.paper_id for claim in self.claims for ref in claim.references}
            if len(papers) < 2 or not self.limitations:
                raise ContractValueError(
                    "Conflicts require multiple papers and explicit limitations"
                )
        return self

    @property
    def sources(self) -> tuple[GroundedSource, ...]:
        return tuple(
            {ref.excerpt_id: ref for claim in self.claims for ref in claim.references}.values()
        )

    def render(self) -> str:
        heading = {
            "supported": "Evidence-supported synthesis",
            "insufficient": "Insufficient evidence",
            "conflicting": "Conflicting evidence",
        }[self.status]
        lines = [f"## {heading}"]
        lines.extend(
            f"- {claim.text} [{', '.join(ref.excerpt_id for ref in claim.references)}]"
            for claim in self.claims
        )
        lines.extend(f"- {limitation}" for limitation in self.limitations)
        lines.append("Reference checks establish quote and artifact identity, not claim truth.")
        return "\n\n".join(lines)


def parse_grounded_answer(raw: str, sources: tuple[GroundedSource, ...]) -> GroundedAnswer:
    answer = GroundedAnswer.model_validate_json(raw)
    allowed = {source.excerpt_id: source for source in sources}
    for claim in answer.claims:
        for reference in claim.references:
            if allowed.get(reference.excerpt_id) != reference:
                raise ContractValueError("Claim references must exactly match supplied evidence")
    return answer


def verify_source(
    source: GroundedSource, markdown: bytes | None
) -> Literal["valid", "stale", "missing"]:
    if markdown is None:
        return "missing"
    if hashlib.sha256(markdown).hexdigest() != source.markdown_sha256:
        return "stale"
    if markdown[source.byte_start : source.byte_end] != source.quote.encode():
        return "stale"
    try:
        sections = _section_excerpts(markdown.decode("utf-8"), 2400, 8)
    except UnicodeError:
        return "stale"
    for index, (section, start, end, quote) in enumerate(sections, start=1):
        if (section, start, end, quote) == (
            source.section,
            source.byte_start,
            source.byte_end,
            source.quote,
        ):
            expected_id = f"{source.paper_id}:{source.markdown_sha256[:12]}:e{index:03d}"
            return "valid" if source.excerpt_id == expected_id else "stale"
    return "stale"
