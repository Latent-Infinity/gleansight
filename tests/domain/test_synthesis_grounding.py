from __future__ import annotations

import hashlib
import json

import pytest

from papers.domain.synthesis_grounding import (
    GroundedSource,
    parse_grounded_answer,
    verify_source,
)


def source() -> GroundedSource:
    text = "# Results\nTreatment improved accuracy."
    quote = "Treatment improved accuracy."
    return GroundedSource(
        excerpt_id=f"p1:{hashlib.sha256(text.encode()).hexdigest()[:12]}:e001",
        paper_id="p1",
        title="Trial",
        section="Results",
        byte_start=10,
        byte_end=len(text.encode()),
        quote=quote,
        sha256=hashlib.sha256(quote.encode()).hexdigest(),
        markdown_sha256=hashlib.sha256(text.encode()).hexdigest(),
        page=None,
    )


def payload(reference: GroundedSource) -> dict:
    return {
        "status": "supported",
        "claims": [{"text": "Accuracy improved.", "references": [reference.model_dump()]}],
        "limitations": [],
    }


def test_claim_requires_exact_supplied_quote_and_locator() -> None:
    ref = source()
    result = parse_grounded_answer(json.dumps(payload(ref)), (ref,))
    assert result.claims[0].references == (ref,)
    for field, value in [
        ("paper_id", "outside"),
        ("section", "Wrong"),
        ("byte_start", 0),
        ("markdown_sha256", "0" * 64),
        ("quote", "Invented quotation"),
    ]:
        raw = payload(ref)
        raw["claims"][0]["references"][0][field] = value
        with pytest.raises(ValueError):
            parse_grounded_answer(json.dumps(raw), (ref,))


def test_unsupported_answer_and_false_conflict_fail() -> None:
    ref = source()
    for raw in [
        "An uncited answer.",
        '{"status":"supported","claims":[],"limitations":[]}',
        json.dumps({**payload(ref), "status": "conflicting"}),
    ]:
        with pytest.raises(ValueError):
            parse_grounded_answer(raw, (ref,))


def test_changed_markdown_is_stale_even_when_quote_survives() -> None:
    ref = source()
    assert verify_source(ref, b"# Results\nTreatment improved accuracy.") == "valid"
    assert verify_source(ref, b"# Results\nTreatment improved accuracy.\nNew") == "stale"
    assert verify_source(ref, None) == "missing"


def test_explicit_insufficient_and_conflicting_evidence() -> None:
    ref = source()
    second = ref.model_copy(update={"paper_id": "p2", "excerpt_id": "p2:e001"})
    unsupported = {
        "status": "insufficient",
        "claims": [],
        "limitations": ["These papers do not report long-term outcomes."],
    }
    result = parse_grounded_answer(json.dumps(unsupported), (ref,))
    assert result.status == "insufficient"
    assert not result.sources
    conflict = {
        "status": "conflicting",
        "claims": [
            {"text": "One study reports improvement.", "references": [ref.model_dump()]},
            {"text": "A second study disagrees.", "references": [second.model_dump()]},
        ],
        "limitations": ["Study populations differ; the conflict cannot be resolved."],
    }
    result = parse_grounded_answer(json.dumps(conflict), (ref, second))
    assert result.status == "conflicting"
    assert len(result.sources) == 2
    assert "Conflicting evidence" in result.render()


def test_uncited_claim_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_grounded_answer(
            json.dumps(
                {
                    "status": "supported",
                    "claims": [{"text": "Unsupported conclusion", "references": []}],
                    "limitations": [],
                }
            ),
            (),
        )


@pytest.mark.parametrize(
    "field,value", [("section", "Invented section"), ("excerpt_id", "spoofed-source")]
)
def test_verification_rejects_forged_locator(field: str, value: str) -> None:
    ref = source().model_copy(update={field: value})
    assert verify_source(ref, b"# Results\nTreatment improved accuracy.") == "stale"


def test_insufficient_status_cannot_hide_claims() -> None:
    raw = payload(source())
    raw["status"] = "insufficient"
    with pytest.raises(ValueError):
        parse_grounded_answer(json.dumps(raw), (source(),))
