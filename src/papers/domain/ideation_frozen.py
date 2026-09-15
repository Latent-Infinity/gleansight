from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ValidationError as PydanticValidationError

from papers.domain.errors import OutputValidationFailed
from papers.domain.ideation import EvidenceMap, GenerationOutput
from papers.domain.ideation_bundle import read_verified_text
from papers.domain.ideation_validation import (
    IdeationValidationContext,
    parse_critique_json,
    parse_generation_json,
)
from papers.domain.investigation_evidence import CompletionStr, ContractModel, NonEmptyStr


class IdeationBundleProvenance(ContractModel):
    created_at: NonEmptyStr
    project_id: NonEmptyStr
    question: NonEmptyStr
    generation_model: CompletionStr
    critic_model: CompletionStr
    llm_calls: Literal[2]
    full_text_analyzed: Literal[False]
    literature_search_performed: Literal[False]
    human_approval_claimed: Literal[False]
    hashes_are_authenticated_provenance: Literal[False]


def load_frozen_ideation_inputs(
    bundle: Path, source_hashes: dict[str, str]
) -> tuple[EvidenceMap, GenerationOutput]:
    try:
        evidence = EvidenceMap.model_validate_json(
            read_verified_text(bundle / "evidence-map.json", source_hashes["evidence-map.json"])
        )
        provenance = IdeationBundleProvenance.model_validate_json(
            read_verified_text(bundle / "provenance.json", source_hashes["provenance.json"])
        )
        generation_payload = read_verified_text(bundle / "ideas.json", source_hashes["ideas.json"])
        critique_payload = read_verified_text(
            bundle / "critique.json", source_hashes["critique.json"]
        )
    except (KeyError, PydanticValidationError) as exc:
        raise OutputValidationFailed("frozen ideation bundle failed validation") from exc
    if evidence.project_id != provenance.project_id:
        raise OutputValidationFailed("frozen ideation project does not match provenance")
    generation = parse_generation_json(
        generation_payload,
        IdeationValidationContext(
            expected_question=provenance.question,
            allowed_excerpt_ids=frozenset(excerpt.excerpt_id for excerpt in evidence.excerpts),
        ),
    )
    parse_critique_json(
        critique_payload,
        frozenset(idea.idea_id for idea in generation.ideas),
        frozenset(excerpt.excerpt_id for excerpt in evidence.excerpts),
    )
    return evidence, generation
