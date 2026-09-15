from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError as PydanticValidationError

from papers.domain.errors import OutputValidationFailed
from papers.domain.ideation import Critique, GenerationOutput
from papers.domain.policies import parse_structured_json


@dataclass(frozen=True, slots=True)
class IdeationValidationContext:
    expected_question: str
    allowed_excerpt_ids: frozenset[str]


def parse_generation_json(payload: str, context: IdeationValidationContext) -> GenerationOutput:
    try:
        output = GenerationOutput.model_validate(parse_structured_json(payload))
    except PydanticValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors(include_input=False)
        )
        raise OutputValidationFailed(f"ideation generation failed validation: {summary}") from exc
    if (
        " ".join(output.question.split()).casefold()
        != " ".join(context.expected_question.split()).casefold()
    ):
        raise OutputValidationFailed("ideation question does not match request")
    cited = {excerpt_id for card in output.evidence_cards for excerpt_id in card.excerpt_ids} | {
        excerpt_id for idea in output.ideas for excerpt_id in idea.citation_excerpt_ids
    }
    if not cited.issubset(context.allowed_excerpt_ids):
        raise OutputValidationFailed("ideation cited excerpts outside frozen evidence")
    return output


def parse_critique_json(
    payload: str,
    known_idea_ids: frozenset[str],
    allowed_excerpt_ids: frozenset[str],
) -> Critique:
    try:
        critique = Critique.model_validate(parse_structured_json(payload))
    except PydanticValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors(include_input=False)
        )
        raise OutputValidationFailed(f"ideation critique failed validation: {summary}") from exc
    returned_ids = [review.idea_id for review in critique.reviews]
    if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != known_idea_ids:
        raise OutputValidationFailed("critique must cover exactly the generated idea IDs")
    duplicates = {
        review.idea_id: review.duplicate_of
        for review in critique.reviews
        if review.duplicate_of is not None
    }
    if not set(duplicates.values()).issubset(known_idea_ids):
        raise OutputValidationFailed("critique duplicate_of references an unknown idea")
    cited = {
        excerpt_id for review in critique.reviews for excerpt_id in review.evidence_excerpt_ids
    }
    if not cited.issubset(allowed_excerpt_ids):
        raise OutputValidationFailed("critique cited excerpts outside frozen evidence")
    for origin in duplicates:
        seen: set[str] = set()
        current: str | None = origin
        while current is not None:
            if current in seen:
                raise OutputValidationFailed("critique duplicate graph must be acyclic")
            seen.add(current)
            current = duplicates.get(current)
    return critique
