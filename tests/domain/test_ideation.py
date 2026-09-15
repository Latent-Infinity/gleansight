from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from papers.domain.errors import OutputValidationFailed
from papers.domain.ideation import (
    Critique,
    EvidenceMap,
    GenerationOutput,
)
from papers.domain.ideation_evidence import build_evidence_map
from papers.domain.ideation_validation import (
    IdeationValidationContext,
    parse_critique_json,
    parse_generation_json,
)


def _generation_payload() -> dict:
    return {
        "question": "What should we investigate?",
        "evidence_cards": [
            {
                "card_id": "card-1",
                "category": "method",
                "claim_kind": "paper_claim",
                "statement": "The paper uses masked prediction.",
                "excerpt_ids": ["paper-1:e001"],
                "uncertainty": None,
            }
        ],
        "ideas": [
            {
                "idea_id": "idea-1",
                "title": "Test temporal masking",
                "gap": "Mask schedules are not compared.",
                "mechanism": "Vary mask schedules while holding capacity fixed.",
                "citation_excerpt_ids": ["paper-1:e001"],
                "known_overlap": "Overlaps with masked prediction, but changes schedule.",
                "falsifiable_question": "Does adaptive masking improve held-out error?",
                "smallest_test": "Compare two schedules on one public split.",
                "data_assumptions": "A public split is available.",
                "model_assumptions": "The implementation exposes mask schedules.",
                "compute_assumptions": "Two single-GPU pilot runs.",
                "feasibility_uncertainty": "Exact memory and runtime are unknown.",
            }
        ],
    }


def _context() -> IdeationValidationContext:
    return IdeationValidationContext(
        expected_question="What should we investigate?",
        allowed_excerpt_ids=frozenset({"paper-1:e001"}),
    )


def test_generation_accepts_zero_ideas() -> None:
    payload = _generation_payload()
    payload["ideas"] = []

    result = parse_generation_json(__import__("json").dumps(payload), _context())

    assert result.ideas == ()


def test_generation_accepts_null_unknown_assumptions() -> None:
    payload = _generation_payload()
    payload["ideas"][0]["known_overlap"] = None
    payload["ideas"][0]["data_assumptions"] = None
    payload["ideas"][0]["model_assumptions"] = None
    payload["ideas"][0]["compute_assumptions"] = None

    result = parse_generation_json(__import__("json").dumps(payload), _context())

    assert result.ideas[0].data_assumptions is None


def test_generation_accepts_unknown_card_with_descriptive_statement() -> None:
    payload = _generation_payload()
    payload["evidence_cards"][0] = {
        "card_id": "card-1",
        "category": "data",
        "claim_kind": "unknown",
        "statement": "The selected excerpts do not identify a public data split.",
        "excerpt_ids": [],
        "uncertainty": "Full paper text was not analyzed.",
    }

    result = parse_generation_json(__import__("json").dumps(payload), _context())

    assert result.evidence_cards[0].claim_kind.value == "unknown"


def test_generation_rejects_unknown_excerpt_citation() -> None:
    payload = _generation_payload()
    payload["ideas"][0]["citation_excerpt_ids"] = ["paper-2:e001"]

    with pytest.raises(OutputValidationFailed, match="outside frozen evidence"):
        parse_generation_json(__import__("json").dumps(payload), _context())


def test_generation_rejects_more_than_six_ideas() -> None:
    payload = _generation_payload()
    payload["ideas"] = [
        {**deepcopy(payload["ideas"][0]), "idea_id": f"idea-{index}"} for index in range(7)
    ]

    with pytest.raises(OutputValidationFailed, match="generation failed validation"):
        parse_generation_json(__import__("json").dumps(payload), _context())


def test_critique_requires_exact_known_idea_ids() -> None:
    payload = {"reviews": []}

    with pytest.raises(OutputValidationFailed, match="exactly the generated idea IDs"):
        parse_critique_json(
            __import__("json").dumps(payload),
            frozenset({"idea-1"}),
            frozenset({"paper-1:e001"}),
        )


def test_critique_accepts_empty_reviews_when_generation_has_zero_ideas() -> None:
    result = parse_critique_json('{"reviews": []}', frozenset(), frozenset())

    assert result.reviews == ()


def test_critique_rejects_duplicate_cycle() -> None:
    payload = {
        "reviews": [
            {
                "idea_id": "idea-1",
                "verdict": "revise",
                "rationale": "Substantially overlaps idea 2.",
                "overlap": "Same intervention.",
                "contradiction": None,
                "uncertainty": "Need direct comparison.",
                "duplicate_of": "idea-2",
                "evidence_excerpt_ids": ["paper-1:e001"],
            },
            {
                "idea_id": "idea-2",
                "verdict": "revise",
                "rationale": "Substantially overlaps idea 1.",
                "overlap": "Same intervention.",
                "contradiction": None,
                "uncertainty": "Need direct comparison.",
                "duplicate_of": "idea-1",
                "evidence_excerpt_ids": ["paper-1:e001"],
            },
        ]
    }

    with pytest.raises(OutputValidationFailed, match="acyclic"):
        parse_critique_json(
            __import__("json").dumps(payload),
            frozenset({"idea-1", "idea-2"}),
            frozenset({"paper-1:e001"}),
        )


def test_critique_rejects_unknown_evidence_excerpt() -> None:
    payload = {
        "reviews": [
            {
                "idea_id": "idea-1",
                "verdict": "keep",
                "rationale": "The comparison is falsifiable.",
                "overlap": None,
                "contradiction": None,
                "uncertainty": "Feasibility remains unmeasured.",
                "duplicate_of": None,
                "evidence_excerpt_ids": ["invented:e999"],
            }
        ]
    }

    with pytest.raises(OutputValidationFailed, match="outside frozen evidence"):
        parse_critique_json(
            __import__("json").dumps(payload),
            frozenset({"idea-1"}),
            frozenset({"paper-1:e001"}),
        )


def test_provider_schemas_are_recursively_strict() -> None:
    for schema in (GenerationOutput.model_json_schema(), Critique.model_json_schema()):
        assert schema["additionalProperties"] is False
        for definition in schema["$defs"].values():
            if definition.get("type") == "object":
                assert set(definition["required"]) == set(definition["properties"])
                assert definition["additionalProperties"] is False


def test_evidence_map_rejects_excerpt_hash_mismatch() -> None:
    payload = {
        "project_id": "project-1",
        "project_name": "Project",
        "inventory": [
            {
                "paper_id": "paper-1",
                "title": "Paper",
                "markdown_missing": False,
                "partial": True,
                "markdown_bytes": 20,
                "selected_bytes": 5,
                "selected_excerpt_ids": ["paper-1:e001"],
            }
        ],
        "excerpts": [
            {
                "excerpt_id": "paper-1:e001",
                "paper_id": "paper-1",
                "title": "Paper",
                "section": "Abstract",
                "byte_start": 0,
                "byte_end": 5,
                "sha256": "0" * 64,
                "quote": "hello",
            }
        ],
        "coverage_note": "Only selected excerpts were analyzed.",
    }

    with pytest.raises(ValidationError, match="hash"):
        EvidenceMap.model_validate(payload)


def test_evidence_builder_records_missing_and_partial_inventory(tmp_path: Path) -> None:
    markdown = tmp_path / "paper.md"
    markdown.write_text("# Method\n" + "a" * 30 + "\n# Limits\n" + "b" * 30)

    evidence = build_evidence_map(
        "project-1",
        "Project",
        ["paper-1", "paper-2"],
        {"paper-1": ("Readable", markdown), "paper-2": ("Missing", None)},
        excerpt_bytes=10,
        max_excerpts_per_paper=1,
    )

    assert evidence.inventory[0].partial is True
    assert evidence.inventory[1].markdown_missing is True
    excerpt = evidence.excerpts[0]
    source_bytes = markdown.read_bytes()
    assert source_bytes[excerpt.byte_start : excerpt.byte_end] == excerpt.quote.encode()
    assert excerpt.excerpt_id == "paper-1:e001"
