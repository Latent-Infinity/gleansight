from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
PROJECTION_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-projection-review-2026-08-28" / "final"


def _json(name: str) -> dict[str, Any]:
    value = json.loads((PACKET_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _jsonl(name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (PACKET_ROOT / name).read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        assert isinstance(row, dict)
        rows.append(row)
    return rows


def _canonical_sha256(value: object) -> str:
    preimage = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(preimage).hexdigest()


def test_jepa_packet_is_digest_bound_and_report_only() -> None:
    summary = _json("review-summary.json")
    assert summary["packet_kind"] == "research_result_report"
    assert summary["authorization_state"] == "report_only"
    assert summary["runtime_authorized"] is False
    assert summary["evidence_sufficient"] is False
    assert summary["corpus_fact_writes"] == 0
    assert summary["operator_activation_requested"] is False
    review = summary["independent_review"]
    assert review["completed_rounds"] == 4
    assert review["current_decision"] == "approve_report_only"
    assert summary["review_decision"] == "approved_report_only"
    artifact_sha256 = summary["artifact_sha256"]
    assert isinstance(artifact_sha256, dict)
    assert set(artifact_sha256) == {
        "ablation-results.json",
        "prior-art-checks.jsonl",
        "results.json",
        "source-ledger.json",
    }
    for name, expected_digest in artifact_sha256.items():
        assert isinstance(name, str)
        assert hashlib.sha256((PACKET_ROOT / name).read_bytes()).hexdigest() == expected_digest
    assert summary["packet_digest_algorithm"] == "sha256(canonical_json(artifact_sha256))"
    assert summary["packet_digest"] == _canonical_sha256(artifact_sha256)


def test_jepa_source_ledger_binds_the_approved_finance_corpus() -> None:
    ledger = _json("source-ledger.json")
    records = ledger["records"]
    assert isinstance(records, list)
    assert [record["record_id"] for record in records] == [
        "N11-FIN-01",
        "N11-FIN-02",
        "N11-FIN-03",
        "N11-FIN-04",
        "N11-FIN-05",
    ]
    assert records[0]["corpus_role"] == "direct_jepa"
    assert all(record["corpus_role"] == "adjacent_finance_evidence" for record in records[1:])
    for record in records:
        path = PROJECTION_ROOT / record["projection_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["projection_sha256"]
        excerpt_path = PROJECTION_ROOT / record["approved_excerpt"]
        assert (
            hashlib.sha256(excerpt_path.read_bytes()).hexdigest()
            == record["approved_excerpt_sha256"]
        )
        assert record["domain_policy_id"] == "finance/1"
        assert record["review_status"] == "approved"


def test_jepa_results_separate_facts_gaps_ideas_and_axis_hypothesis() -> None:
    results = _json("results.json")
    summary = _json("review-summary.json")
    facts = results["extracted_facts"]
    gaps = results["inferred_gaps"]
    ideas = results["proposed_ideas"]
    assert isinstance(facts, list)
    assert isinstance(gaps, list)
    assert isinstance(ideas, list)
    assert len(facts) == 10
    assert len(gaps) == 4
    assert len(ideas) == 3
    assert summary["result_counts"] == {
        "extracted_facts": len(facts),
        "inferred_gaps": len(gaps),
        "proposed_ideas": len(ideas),
        "candidate_axis_hypotheses": 1,
    }
    fact_ids = {fact["fact_id"] for fact in facts}
    assert all(fact["result_class"] == "extracted_fact" for fact in facts)
    assert all(fact["source_basis"] == "approved_projection" for fact in facts)
    records = {record["record_id"]: record for record in _json("source-ledger.json")["records"]}
    for fact in facts:
        record = records[fact["source_record_id"]]
        assert fact["source_location"].startswith(
            (record["projection_path"], record["approved_excerpt"])
        )
    for gap in gaps:
        assert gap["result_class"] == "inferred_gap"
        assert len(gap["supporting_fact_ids"]) >= 2
        assert set(gap["supporting_fact_ids"]) <= fact_ids
        assert gap["uncertainty"]
    snapshot = results["cooccurrence_snapshot"]
    snapshot_preimage = {
        "record_ids": snapshot["record_ids"],
        "feature_matrix": snapshot["feature_matrix"],
        "feature_evidence": snapshot["feature_evidence"],
    }
    assert snapshot["snapshot_id"] == _canonical_sha256(snapshot_preimage)
    for record_id, features in snapshot["feature_matrix"].items():
        for feature in features:
            evidence_ids = snapshot["feature_evidence"][f"{record_id}:{feature}"]
            assert evidence_ids
            assert set(evidence_ids) <= fact_ids
    for idea in ideas:
        assert idea["result_class"] == "proposed_idea"
        assert idea["track"] == "same_policy:finance/1"
        assert len(idea["supporting_fact_ids"]) >= 2
        assert set(idea["supporting_fact_ids"]) <= fact_ids
        assert idea["cooccurrence_snapshot_id"] == snapshot["snapshot_id"]
        assert idea["atypicality"]["interpretation"] == "corpus rarity only; not novelty or value"
        assert idea["mechanistic_bridge"]
        assert idea["falsifiable_test"]["primary_metric"]
        assert idea["prior_art_status"] == "partial_overlap"
        assert idea["decision"] == "review"
        assert idea["runtime_authorized"] is False
    axis = results["candidate_axis_hypothesis"]
    assert axis["axis_id"] == "validation_target"
    assert axis["status"] == "needs_more_corpus"
    assert axis["schema_admission_recommended"] is False


def test_jepa_prior_art_rows_do_not_claim_novelty_from_search_absence() -> None:
    rows = _jsonl("prior-art-checks.jsonl")
    assert {row["candidate_id"] for row in rows} == {"JEPA-IDEA-01", "JEPA-IDEA-02", "JEPA-IDEA-03"}
    for row in rows:
        assert row["cutoff_utc"] == "2026-09-01T00:00:00Z"
        assert row["query_scope"]
        assert row["nearest_prior_art"]
        assert row["novelty_claim"] == "not_established"
        assert row["absence_interpretation"] == "bounded search absence is not proof of novelty"
        assert row["manual_review_completed"] is True


def test_jepa_ablation_keeps_controls_and_activation_separate() -> None:
    ablation = _json("ablation-results.json")
    assert ablation["track"] == "same_policy:finance/1"
    assert ablation["candidate_count"] == 3
    assert ablation["controls"] == ["single_paper_future_work", "rarity_only_negative_control"]
    assert ablation["operator_a_baseline_status"] == "not_executed"
    assert ablation["operator_b_baseline_status"] == "not_executed"
    assert ablation["method_recommendation"] == "report_only_cross_paper_mechanistic_bridge"
    assert ablation["runtime_authorized"] is False
    assert ablation["evidence_sufficient_for_operator_e"] is False
