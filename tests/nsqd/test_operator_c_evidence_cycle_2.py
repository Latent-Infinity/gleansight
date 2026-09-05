from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVATION_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-2026-09-05"


def _json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, Mapping)
    return {str(key): item for key, item in value.items()}


def test_second_operator_c_cycle_is_digest_bound_and_latest() -> None:
    packet = yaml.safe_load((ACTIVATION_ROOT / "operator-c.yaml").read_text(encoding="utf-8"))
    assert packet["latest_evidence_report"] == (
        "../nsqd-operator-c-evidence-2026-09-05/review-summary.json"
    )
    summary = _json(EVIDENCE_ROOT / "review-summary.json")
    artifacts = _mapping(summary["artifact_sha256"])
    assert set(artifacts) == {
        "evidence-ledger.json",
        "claim-extractions.jsonl",
        "direct-a-to-c-prior-art.jsonl",
        "ablation-results.json",
    }
    for name, digest in artifacts.items():
        assert hashlib.sha256((EVIDENCE_ROOT / name).read_bytes()).hexdigest() == digest
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert summary["packet_digest"] == hashlib.sha256(preimage).hexdigest()
    assert packet["latest_evidence_artifact_sha256"] == artifacts


def test_second_operator_c_cycle_records_bounded_negative_result() -> None:
    ledger = _json(EVIDENCE_ROOT / "evidence-ledger.json")
    extractions = _jsonl(EVIDENCE_ROOT / "claim-extractions.jsonl")
    prior_art = _jsonl(EVIDENCE_ROOT / "direct-a-to-c-prior-art.jsonl")
    ablations = _json(EVIDENCE_ROOT / "ablation-results.json")
    summary = _json(EVIDENCE_ROOT / "review-summary.json")

    assert ledger["cutoff_utc"] == "2026-09-05T00:00:00Z"
    assert ledger["authorization_state"] == "report_only"
    assert ledger["noninteraction_conclusion"] == "unverified_absence_of_evidence_only"
    records = cast(list[dict[str, object]], ledger["records"])
    assert len(records) == 4
    assert {row["source_id"] for row in records} == {
        "arXiv:2605.02701v2",
        "arXiv:2605.26890v1",
        "arXiv:2302.00999v2",
        "arXiv:2411.02947v1",
    }
    assert len(extractions) == 4
    decisions = [row["decision"] for row in extractions]
    assert all(
        isinstance(decision, str) and decision.startswith("rejected") for decision in decisions
    )
    assert any(row["decision"] == "rejected_direct_prior_art" for row in extractions)
    assert {row["pair"] for row in prior_art} == {"primary", "backup"}
    assert ablations["selected_pair"] is None
    assert ablations["candidate_output_count"] == 0
    assert summary["review_decision"] == "insufficient_evidence"
    assert summary["human_acceptance"] == "not_requested"
    assert summary["runtime_activation"] == "not_authorized"
