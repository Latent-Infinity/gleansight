from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVATION_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-2026-09-07"
PACKET_DIGEST = "8eb17c52eaa85cc35618a7008db1c1603f351f3cc4333821994c17d468021d18"
type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
REVIEW_NOTES = [
    (
        "Recomputed SHA-256 for all seven manifest artifacts and the canonical packet "
        "digest; all match review-summary.json. Reacquired all six external receipts from "
        "their exact pinned locators and matched every recorded SHA-256 and byte count."
    ),
    (
        "Verified the exact SC-JEPA v2, Golub v1, OpenReview BZfkxSasd3 version 2, and "
        "Fin-JEPA commit 58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9 identities. All "
        "thirteen quoted extracts are verbatim and receipt-bound; polarity and direction "
        "are materially correct, and hypotheses remain separate from source facts."
    ),
    (
        "Confirmed that SC-JEPA predicts subsequent-window anomaly status while Golub "
        "defines intrinsic-network FX liquidity; the selected sources supply shared "
        "vocabulary but no source-supported typed transfer edge. OpenReview and Fin-JEPA "
        "are valid direct-domain/application-and-citation counterevidence, but not proof "
        "of exact mechanism identity, legal priority, noninteraction, or non-novelty."
    ),
    (
        "Confirmed that missing citation and co-citation evidence and the uninspected "
        "OpenReview full text are disclosed as limitations and absence of evidence only. "
        "Ablation counts reconcile with four hypothesis rows, two counterevidence rows, "
        "and thirteen extracts; the shuffle is reproducible, while relevance, "
        "rediscovery, and error-rate metrics remain explicitly unmeasured rather than "
        "fabricated."
    ),
    (
        "Confirmed that authorization_state=report_only, candidate_outputs=[], "
        "evidence_sufficient=false, human_acceptance=not_requested, "
        "runtime_activation=not_authorized, and operator_d_status=blocked are mutually "
        "consistent. This review approves only the negative and insufficient-evidence "
        "conclusion and grants no Operator C or D authority."
    ),
]


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json(path: Path) -> dict[str, JsonValue]:
    loaded: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(loaded)


def test_cycle_3_review_summary_and_detached_seal_bind_oracle_review() -> None:
    summary_path = EVIDENCE_ROOT / "review-summary.json"
    summary = _json(summary_path)
    review = _mapping(summary["independent_review"])
    seal = _json(EVIDENCE_ROOT / "review-seal.json")

    assert review == {
        "review_status": "approved_negative_conclusion",
        "reviewed_at_utc": "2026-09-07T11:12:48Z",
        "reviewer_agent_type": "read-only strategic technical reviewer",
        "reviewer_id": "openai/gpt-5.6-sol / independent-evidence-reviewer",
        "reviewer_model": "openai/gpt-5.6-sol",
        "review_notes": REVIEW_NOTES,
    }
    assert summary["packet_digest"] == PACKET_DIGEST
    assert seal == {
        "authorization_state": "report_only",
        "human_acceptance": "not_requested",
        "packet_digest": PACKET_DIGEST,
        "review_status": "approved_negative_conclusion",
        "review_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "reviewed_at_utc": "2026-09-07T11:12:48Z",
        "reviewer_id": "openai/gpt-5.6-sol / independent-evidence-reviewer",
        "runtime_activation": "not_authorized",
        "schema_version": 1,
    }


def test_cycle_3_remains_sealed_without_authorizing_operator_c_or_d() -> None:
    packet = yaml.safe_load((ACTIVATION_ROOT / "operator-c.yaml").read_text(encoding="utf-8"))
    assert isinstance(packet, Mapping)
    summary_path = EVIDENCE_ROOT / "review-summary.json"
    seal_path = EVIDENCE_ROOT / "review-seal.json"
    summary = _json(summary_path)
    review = _mapping(summary["independent_review"])

    assert packet["latest_algorithm_identity"] == (
        "operator-c-provenance-bound-primary-source-audit/3"
    )
    assert packet["latest_prompt_identity"] == "operator-c-typed-bridge-review/3"
    assert review["reviewed_at_utc"] == "2026-09-07T11:12:48Z"
    assert packet["latest_executed_at_utc"] == "2026-09-09T20:27:38Z"
    assert isinstance(summary["artifact_sha256"], dict)
    assert (
        _json(seal_path)["review_summary_sha256"]
        == hashlib.sha256(summary_path.read_bytes()).hexdigest()
    )
    historical_cycle = next(
        cycle
        for cycle in packet["evidence_cycles"]
        if cycle["cycle_id"] == "operator-c-evidence-2026-09-07"
    )
    assert historical_cycle == {
        "cycle_id": "operator-c-evidence-2026-09-07",
        "decision": "insufficient_evidence",
        "review_status": "approved_negative_conclusion",
    }
    assert packet["candidate_outputs"] == []
    assert packet["evidence_sufficient"] is False
    assert packet["runtime_authorized"] is False
    assert packet["latest_cycle_results"]["operator_d_status"] == "blocked"
