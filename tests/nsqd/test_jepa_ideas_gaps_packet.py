from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import nsqd.domain.operator_baselines as opb

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
    assert summary["human_usefulness_review"] == {
        "packet_status": "completed",
        "reviewer_identity": "human-reviewer",
        "reviewed_at_utc": "2026-09-02T15:50:20Z",
        "all_scores_null": False,
        "blinded_item_count": 9,
        "duplicate_rationale": "same idea, different targets",
        "duplicate_group_count": 1,
        "descriptive_only": True,
        "statistical_significance_inference": False,
        "raw": {
            "item_count": 9,
            "abstention_count": 0,
            "total_score": 8,
            "mean_score": 0.888889,
        },
        "duplicate_collapsed": {
            "effective_item_count": 7,
            "abstention_count": 0,
            "total_score": 8,
            "mean_score": 1.142857,
        },
        "by_operator": {
            "A": {"raw_scores": [2, 2, 1], "collapsed_scores": [2, 2, 1], "mean_score": 1.666667},
            "B": {"raw_scores": [0, 0, 0], "collapsed_scores": [0], "mean_score": 0.0},
            "E": {"raw_scores": [1, 1, 1], "collapsed_scores": [1, 1, 1], "mean_score": 1.0},
        },
    }
    assert summary["accounting_revision"] == {
        "revised_at_utc": "2026-09-03T16:00:38Z",
        "structural_screen_status": "executed",
        "matched_count_operator_baselines_status": "executed_report_only",
        "human_usefulness_review_status": "completed",
        "operator_e_authorization_state": "unauthorized",
        "operator_e_broader_prior_art_status": "completed_report_only",
    }
    prior = summary["prior_report_review"]
    assert prior["completed_rounds"] == 4
    assert prior["final_reviewed_at_utc"] == "2026-09-01T16:25:59Z"
    assert summary["current_execution_bundle_review"]["status"] == "passed"
    assert summary["broader_prior_art_review"] == {
        "covers_artifacts": ["operator-e-broader-prior-art.json"],
        "human_evidence_sufficiency_decision": "approved_for_experimental_implementation",
        "human_decided_at_utc": "2026-09-03T16:00:38Z",
        "reviewed_at_utc": "2026-09-03T09:31:53Z",
        "reviewer_scope": "independent_agent_technical_review",
        "runtime_authorization_decision": "authorized_experimental_pending_implementation",
        "runtime_authorization_effective": False,
        "status": "passed_report_only_technical_review",
    }
    assert summary["review_decision"] == "completed_human_review_report_only"
    artifact_sha256 = summary["artifact_sha256"]
    assert isinstance(artifact_sha256, dict)
    assert set(artifact_sha256) == {
        "ablation-results.json",
        "baseline-evidence.json",
        "blinded-review-audit-manifest.json",
        "blinded-review-packet.json",
        "operator-e-broader-prior-art.json",
        "operator-e-report-only-candidates.json",
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
    assert summary["report_only_artifact_counts"] == {
        "operator_a_baseline_cards": 3,
        "operator_b_baseline_cards": 3,
        "operator_e_candidate_artifacts": 3,
        "blinded_review_items": 9,
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
    accounting = ablation["execution_accounting"]
    assert accounting["structural_screen_status"] == "executed"
    assert accounting["structural_screen_methods"] == [
        "cross_paper_mechanistic_bridge",
        "single_paper_future_work",
        "rarity_only_negative_control",
    ]
    assert accounting["matched_candidate_count_per_method"] == 3
    assert accounting["operator_a_matched_count_baseline_status"] == "executed_report_only"
    assert accounting["operator_b_matched_count_baseline_status"] == "executed_report_only"
    assert accounting["reviewed_usefulness_at_matched_candidate_count"] == {
        "raw_mean": 0.888889,
        "duplicate_collapsed_mean": 1.142857,
    }
    assert accounting["usefulness_review_status"] == "completed_human_review"
    assert accounting["operator_e_authorization_state"] == "unauthorized"
    assert ablation["controls"] == ["single_paper_future_work", "rarity_only_negative_control"]
    assert ablation["operator_a_baseline_status"] == "executed_report_only"
    assert ablation["operator_b_baseline_status"] == "executed_report_only"
    assert ablation["operator_e_candidate_status"] == "derived_report_only"
    assert accounting["operator_e_broader_prior_art_status"] == "completed_report_only"
    assert ablation["method_recommendation"] == "report_only_cross_paper_mechanistic_bridge"
    assert ablation["runtime_authorized"] is False
    assert ablation["evidence_sufficient_for_operator_e"] is False

    readme = (PACKET_ROOT / "README.md").read_text(encoding="utf-8")
    assert "JEPA structural screen" in readme
    assert "real Diverge → Ground → Score report-only baseline cards" in readme
    assert "blinded 9-item human usefulness packet" in readme
    assert "human usefulness review" in readme
    assert "operator-e-broader-prior-art.json" in readme


def test_jepa_review_summary_separates_prior_report_review_from_new_execution_bundle() -> None:
    summary = _json("review-summary.json")
    prior = summary["prior_report_review"]
    current = summary["current_execution_bundle_review"]
    assert prior["final_reviewed_at_utc"] == "2026-09-01T16:25:59Z"
    assert prior["scope"] == (
        "results.json, source-ledger.json, prior-art-checks.jsonl, "
        "and the pre-baseline structural report"
    )
    assert current["status"] == "passed"
    assert current["reviewer_id"] == "independent-agent-review"
    assert current["covers_artifacts"] == [
        "baseline-evidence.json",
        "operator-e-report-only-candidates.json",
        "blinded-review-packet.json",
        "blinded-review-audit-manifest.json",
        "ablation-results.json",
    ]
    assert summary["broader_prior_art_review"] == {
        "covers_artifacts": ["operator-e-broader-prior-art.json"],
        "human_evidence_sufficiency_decision": "approved_for_experimental_implementation",
        "human_decided_at_utc": "2026-09-03T16:00:38Z",
        "reviewed_at_utc": "2026-09-03T09:31:53Z",
        "reviewer_scope": "independent_agent_technical_review",
        "runtime_authorization_decision": "authorized_experimental_pending_implementation",
        "runtime_authorization_effective": False,
        "status": "passed_report_only_technical_review",
    }
    assert "replaced sketch-only matched-count rows" not in prior["resolved_findings"]


def test_jepa_blinded_packet_describes_operator_label_blinding_with_limits() -> None:
    packet = _json("blinded-review-packet.json")
    assert packet["blinding_scope"] == "operator_label_blinded"
    assert packet["human_usefulness_review_status"] == "completed"
    assert packet["blinding_limitation"] == (
        "proposal content is retained for usefulness scoring and may still permit family inference"
    )
    assert "family-inference-proof" not in json.dumps(packet, sort_keys=True)


def test_jepa_snapshot_provenance_is_truthful_about_corpus_scope_and_filtering() -> None:
    baseline = _json("baseline-evidence.json")
    readme = (PACKET_ROOT / "README.md").read_text(encoding="utf-8")
    summary = _json("review-summary.json")
    blinded = _json("blinded-review-packet.json")

    assert baseline["source_snapshot"] == {
        "snapshot_id": "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5",
        "corpus_version": 11,
        "snapshot_state": "production_valid",
        "snapshot_scope": "approved_corpus_snapshot",
        "approved_record_count": 11,
        "filtered_domain_policy_id": "finance/1",
        "filtered_record_count": 6,
    }
    assert blinded["source_snapshot_id"] == baseline["source_snapshot"]["snapshot_id"]
    assert "approved corpus snapshot" in readme
    assert "finance/1 filtering" in readme
    assert any(
        "approved corpus snapshot" in limitation for limitation in summary["known_limitations"]
    )


def test_resealing_digests_cannot_hide_tampered_blinded_review_content() -> None:
    results = _json("results.json")
    baseline = _json("baseline-evidence.json")
    e_candidates = _json("operator-e-report-only-candidates.json")
    blinded = _json("blinded-review-packet.json")
    audit = _json("blinded-review-audit-manifest.json")
    summary = _json("review-summary.json")

    tampered = json.loads(json.dumps(blinded))
    tampered["items"][0]["proposal_summary"] += " Tampered after review packet generation."
    tampered["packet_digest"] = opb.blinded_review_packet_digest(tampered)  # noqa: SLF001

    resealed_audit = json.loads(json.dumps(audit))
    resealed_audit["review_packet_digest"] = tampered["packet_digest"]
    resealed_audit["manifest_digest"] = opb.audit_manifest_digest(resealed_audit)  # noqa: SLF001

    resealed_summary = json.loads(json.dumps(summary))
    resealed_summary["artifact_sha256"]["blinded-review-packet.json"] = hashlib.sha256(
        json.dumps(tampered, indent=2, sort_keys=True).encode()
    ).hexdigest()
    resealed_summary["artifact_sha256"]["blinded-review-audit-manifest.json"] = hashlib.sha256(
        json.dumps(resealed_audit, indent=2, sort_keys=True).encode()
    ).hexdigest()
    resealed_summary["packet_digest"] = _canonical_sha256(resealed_summary["artifact_sha256"])
    assert resealed_summary["packet_digest"]

    with pytest.raises(ValueError, match="blinded review item content"):
        opb.evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=tampered,
            audit_manifest=resealed_audit,
        )


def test_jepa_operator_e_candidates_expose_nearest_prior_and_review_contract() -> None:
    packet = _json("operator-e-report-only-candidates.json")
    readme = (PACKET_ROOT / "README.md").read_text(encoding="utf-8")
    for candidate in packet["candidates"]:
        assert candidate["nearest_prior_combinations"] == []
        assert (
            candidate["atypicality"]["interpretation"] == opb.OPERATOR_E_ATYPICALITY_INTERPRETATION
        )
    assert "test_operator_e_cooccurrence.py" in readme
    assert "test_operator_baselines.py" in readme
