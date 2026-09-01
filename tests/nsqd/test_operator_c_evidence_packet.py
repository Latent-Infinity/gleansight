from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVATION_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-2026-08-31"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, Mapping)
    assert all(isinstance(key, str) for key in value)
    return {str(key): item for key, item in value.items()}


def test_operator_c_evidence_report_remains_unauthorized() -> None:
    packet = yaml.safe_load((ACTIVATION_ROOT / "operator-c.yaml").read_text(encoding="utf-8"))
    assert packet["packet_kind"] == "evidence_report"
    assert packet["authorization_state"] == "report_only"
    assert packet["runtime_authorized"] is False
    assert packet["evidence_sufficient"] is False
    assert packet["candidate_outputs"] == []
    assert packet["algorithm_identity"] == "operator-c-evidence-audit/1"
    assert packet["evidence_report"] == "../nsqd-operator-c-evidence-2026-08-31/review-summary.json"


def test_operator_c_evidence_artifacts_are_digest_bound() -> None:
    packet = yaml.safe_load((ACTIVATION_ROOT / "operator-c.yaml").read_text(encoding="utf-8"))
    report_path = (ACTIVATION_ROOT / packet["evidence_report"]).resolve()
    assert report_path == EVIDENCE_ROOT / "review-summary.json"
    summary = _json(report_path)
    artifact_sha256 = summary["artifact_sha256"]
    assert isinstance(artifact_sha256, dict)
    expected = {
        "evidence-ledger.json",
        "claim-extractions.jsonl",
        "direct-a-to-c-prior-art.jsonl",
        "ablation-results.json",
    }
    assert set(artifact_sha256) == expected
    for name, digest in artifact_sha256.items():
        assert isinstance(name, str)
        assert isinstance(digest, str)
        assert hashlib.sha256((EVIDENCE_ROOT / name).read_bytes()).hexdigest() == digest
    packet_preimage = json.dumps(
        artifact_sha256,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert summary["packet_digest_algorithm"] == "sha256(canonical_json(artifact_sha256))"
    assert summary["packet_digest"] == hashlib.sha256(packet_preimage).hexdigest()
    assert packet["evidence_artifact_sha256"] == artifact_sha256
    assert packet["review_decision"] == summary["review_decision"]


def test_operator_c_evidence_report_records_negative_result_without_inference() -> None:
    ledger = _json(EVIDENCE_ROOT / "evidence-ledger.json")
    extractions = _jsonl(EVIDENCE_ROOT / "claim-extractions.jsonl")
    prior_art = _jsonl(EVIDENCE_ROOT / "direct-a-to-c-prior-art.jsonl")
    ablations = _json(EVIDENCE_ROOT / "ablation-results.json")
    summary = _json(EVIDENCE_ROOT / "review-summary.json")

    assert ledger["cutoff_utc"] == "2026-08-31T00:00:00Z"
    assert ledger["noninteraction_conclusion"] == "unverified_absence_of_evidence_only"
    records = ledger["records"]
    assert isinstance(records, list)
    assert all("versioned_full_text_url" in _mapping(record) for record in records)
    interaction_checks = ledger["interaction_checks"]
    assert isinstance(interaction_checks, list)
    for interaction in interaction_checks:
        checks = _mapping(_mapping(interaction)["checks"])
        assert set(checks) == {
            "author_overlap",
            "co_citation",
            "direct_citation",
            "direct_mention",
        }
        assert all("status" in _mapping(check) for check in checks.values())
    assert len(extractions) == 7
    assert all(row["decision"] == "rejected" for row in extractions)
    assert all(
        not (
            _mapping(row["a_to_b"])["supported"] is True
            and _mapping(row["b_to_c"])["supported"] is True
        )
        for row in extractions
    )
    for row in extractions:
        for side in ("a_to_b", "b_to_c"):
            source_url = _mapping(row[side])["source_url"]
            quote = _mapping(row[side])["quote"]
            assert isinstance(source_url, str)
            assert isinstance(quote, str)
            assert "..." not in quote
            assert "arxiv.org/pdf/" in source_url or "/blob/58506d6e31ec" in source_url
    robust_update = next(
        row for row in extractions if row["candidate_bridge"] == "robust update control"
    )
    assert _mapping(robust_update["a_to_b"])["quote"] == (
        "In this paper, we propose several algorithms with high-probability convergence results "
        "under less restrictive assumptions."
    )
    assert _mapping(robust_update["a_to_b"])["supported"] is False
    assert _mapping(robust_update["b_to_c"])["quote"] == (
        r"The training loss comprises two terms: a prediction loss $\mathcal{L}_{\text{pred}}$ "
        r"that measures latent-space alignment, and a regularization loss "
        r"$\mathcal{L}_{\text{reg}}$ that prevents representational collapse."
    )
    assert {row["pair"] for row in prior_art} == {"preferred", "backup"}
    assert ablations["selected_pair"] is None
    assert ablations["selected_extraction_method"] is None
    runs = ablations["runs"]
    assert isinstance(runs, list)
    assert len(runs) == 6
    assert all(_mapping(run)["two_sided_supported_count"] == 0 for run in runs)
    assert summary["review_decision"] == "insufficient_evidence"
    assert summary["candidate_output_count"] == 0
    assert summary["human_acceptance"] == "not_requested"
    assert summary["runtime_activation"] == "not_authorized"
