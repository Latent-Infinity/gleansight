from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

import nsqd.domain.operator_baselines as opb
import nsqd.domain.trusted_files as trusted_files
from nsqd.domain.card import card_decision, missing_card_fields
from nsqd.domain.novelty import (
    NOVELTY_TAU_SEMANTICS,
    NOVELTY_THRESHOLD_TAU,
    apply_novelty_threshold,
    novelty_term,
)
from nsqd.domain.operator_baselines import (
    evaluate_matched_count_operator_baselines,
    report_only_operator_e_candidate_hash,
    verify_scratch_execution_receipt,
)
from nsqd.domain.project import canonical_reviewed_projection_digest, normalize_paraphrase
from nsqd.domain.tau_measurement import tau_measurement_artifact_digest
from nsqd.domain.viability import score_dpred, score_dval, score_fals, score_mech, viability

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"


def _json(name: str) -> dict[str, Any]:
    payload = json.loads((PACKET_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_real_matched_count_baselines_bind_scored_cards_and_blinded_review_packet() -> None:
    results = _json("results.json")
    baseline = _json("baseline-evidence.json")
    e_candidates = _json("operator-e-report-only-candidates.json")
    blinded = _json("blinded-review-packet.json")
    audit = _json("blinded-review-audit-manifest.json")

    summary = evaluate_matched_count_operator_baselines(
        results["proposed_ideas"],
        extracted_facts=results["extracted_facts"],
        baseline_execution=baseline,
        operator_e_candidates=e_candidates["candidates"],
        blinded_review_packet=blinded,
        audit_manifest=audit,
    )

    assert summary["matched_candidate_count"] == 3
    assert summary["operator_a_baseline_status"] == "executed_report_only"
    assert summary["operator_b_baseline_status"] == "executed_report_only"
    assert summary["operator_a_candidate_ids"] == ["A-BASE-01", "A-BASE-02", "A-BASE-03"]
    assert summary["operator_b_candidate_ids"] == ["B-BASE-01", "B-BASE-02", "B-BASE-03"]
    assert summary["operator_e_candidate_ids"] == ["E-REPORT-01", "E-REPORT-02", "E-REPORT-03"]
    assert summary["reviewed_usefulness_at_matched_candidate_count"] == {
        "raw_mean": pytest.approx(8 / 9, abs=1e-6),
        "duplicate_collapsed_mean": pytest.approx(8 / 7, abs=1e-6),
    }
    assert summary["usefulness_review_status"] == "completed_human_review"
    assert summary["human_usefulness_review"]["reviewer_identity"] == "human-reviewer"
    assert summary["operator_e_authorization_state"] == "unauthorized"
    assert summary["runtime_authorized"] is False
    assert summary["candidate_combinations"] == []
    assert summary["blinded_review_item_count"] == 9

    assert baseline["source_snapshot"] == {
        "snapshot_id": "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5",
        "corpus_version": 11,
        "snapshot_state": "production_valid",
        "snapshot_scope": "approved_corpus_snapshot",
        "approved_record_count": 11,
        "filtered_domain_policy_id": "finance/1",
        "filtered_record_count": 6,
    }
    assert baseline["embedding_model"] == {
        "provider": "ollama",
        "model_name": "qwen3-embedding:latest",
        "model_id": "qwen3-embedding",
        "model_version": "latest",
        "installed_model_digest": (
            "64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b"
        ),
        "model_blob_sha256": "3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85",
        "embedding_dimension": 4096,
        "distance_metric": "cosine_distance",
        "normalization_policy": "l2",
        "embedded_at_utc": "2026-09-02T06:45:00+00:00",
    }
    assert baseline["scratch_runtime"]["no_production_writes"] is True
    assert baseline["scratch_runtime"]["production_write_paths"] == []
    assert len(baseline["projection_bindings"]) == 6

    assert e_candidates["runtime_authorized"] is False
    assert e_candidates["evidence_sufficient"] is False
    assert [row["artifact_id"] for row in e_candidates["candidates"]] == [
        "E-REPORT-01",
        "E-REPORT-02",
        "E-REPORT-03",
    ]
    assert all(row["human_usefulness_score"] is None for row in e_candidates["candidates"])
    assert [report_only_operator_e_candidate_hash(row) for row in e_candidates["candidates"]] == [
        row["artifact_hash"] for row in e_candidates["candidates"]
    ]

    assert blinded["reviewer_identity"] == "human-reviewer"
    assert blinded["human_usefulness_review_status"] == "completed"
    assert blinded["reviewed_at_utc"] == "2026-09-02T15:50:20Z"
    assert [item["review_form"]["human_usefulness_score"] for item in blinded["items"]] == [
        1,
        2,
        1,
        2,
        0,
        1,
        0,
        0,
        1,
    ]
    assert audit["review_packet_digest"] == blinded["packet_digest"]
    assert audit["all_scores_null"] is False
    assert baseline["execution_receipt"]["candidate_count"] == 6
    assert baseline["execution_receipt"]["card_count"] == 6


def test_real_matched_count_baselines_fail_closed_on_tampered_baseline_rows() -> None:
    results = _json("results.json")
    baseline = _json("baseline-evidence.json")
    e_candidates = _json("operator-e-report-only-candidates.json")
    blinded = _json("blinded-review-packet.json")
    audit = _json("blinded-review-audit-manifest.json")

    tampered_hash = copy.deepcopy(baseline)
    tampered_hash["operator_a_artifacts"][0]["candidate_artifact_hash"] = "0" * 64
    with pytest.raises(ValueError, match="candidate_artifact_hash does not match candidate body"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=tampered_hash,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    tampered_target = copy.deepcopy(baseline)
    tampered_target["operator_b_artifacts"][0]["diverge_proof"]["selected_target_cell"] = (
        "mechanism=flow-driven|target=drawdown|horizon=intraday"
    )
    with pytest.raises(ValueError, match="Operator B target must match ALG-SEL"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=tampered_target,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    with pytest.raises(ValueError, match="ideas is required"):
        evaluate_matched_count_operator_baselines(
            cast(Any, object()),
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_real_matched_count_baselines_reject_tampered_e_artifacts_and_unblinded_packet() -> None:
    results = _json("results.json")
    baseline = _json("baseline-evidence.json")
    e_candidates = _json("operator-e-report-only-candidates.json")
    blinded = _json("blinded-review-packet.json")
    audit = _json("blinded-review-audit-manifest.json")

    tampered_e = copy.deepcopy(e_candidates["candidates"])
    tampered_e[0]["human_usefulness_score"] = 3
    with pytest.raises(ValueError, match="human_usefulness_score must remain null"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=tampered_e,
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    revealed = copy.deepcopy(blinded)
    revealed["items"][0]["proposal_summary"] += " Source record N11-FIN-01 suggested this."
    with pytest.raises(ValueError, match="review packet must stay blinded"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=revealed,
            audit_manifest=audit,
        )

    mismatched_audit = copy.deepcopy(audit)
    mismatched_audit["items"][0]["artifact_hash"] = "f" * 64
    with pytest.raises(ValueError, match="audit manifest item does not match known artifact hash"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=mismatched_audit,
        )


def _payloads() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    results = _json("results.json")
    baseline = _json("baseline-evidence.json")
    e_candidates = _json("operator-e-report-only-candidates.json")
    blinded = _json("blinded-review-packet.json")
    audit = _json("blinded-review-audit-manifest.json")
    return results, baseline, e_candidates, blinded, audit


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "packet_kind", "wrong"
            ),
            "packet_kind",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "authorization_state", "approved"
            ),
            "report_only",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "runtime_authorized", True
            ),
            "runtime_authorized must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "evidence_sufficient", True
            ),
            "evidence_sufficient must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "candidate_combinations", ["x"]
            ),
            "candidate_combinations must be empty",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["source_snapshot"].__setitem__(
                "snapshot_id", "0" * 64
            ),
            "source_snapshot does not match",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["embedding_model"].__setitem__(
                "installed_model_digest", "0" * 12
            ),
            "embedding_model does not match",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["scratch_runtime"].__setitem__(
                "no_production_writes", False
            ),
            "no_production_writes",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["scratch_runtime"].__setitem__(
                "production_write_paths", ["/prod"]
            ),
            "production write paths",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "projection_bindings", baseline["projection_bindings"][:-1]
            ),
            "projection_bindings must contain",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["projection_bindings"][
                0
            ].__setitem__("approved_record_id", "N11-FIN-01"),
            "manifest_path is outside the approved root",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline.__setitem__(
                "operator_a_artifacts", cast(Any, {})
            ),
            "artifact rows are required",
        ),
        (
            lambda results, baseline, e, blinded, audit: results["proposed_ideas"][0].__setitem__(
                "result_class", "fact"
            ),
            "proposed_idea",
        ),
        (
            lambda results, baseline, e, blinded, audit: results["proposed_ideas"][0].__setitem__(
                "runtime_authorized", True
            ),
            "runtime_authorized must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: results["proposed_ideas"][1].__setitem__(
                "candidate_id", results["proposed_ideas"][0]["candidate_id"]
            ),
            "idea candidate_id values must be unique",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][
                0
            ].__setitem__("source_fact_id", ""),
            "source_fact_id is required",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][0][
                "candidate_artifact"
            ].__setitem__("operator", "B"),
            "artifact must set operator A",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][0][
                "candidate_artifact"
            ]["grounding"].__setitem__("snapshot_state", "smoke_only"),
            "grounding must match the persisted candidate artifact grounding",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][0][
                "candidate_artifact"
            ]["novelty"].__setitem__("snapshot_id", "0" * 64),
            "novelty snapshot_id",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][0][
                "scored_card"
            ].__setitem__("archive_cell_key", "bad"),
            "archive_cell_key",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][0][
                "scored_card"
            ].__setitem__(
                "evaluator_run_id",
                baseline["operator_a_artifacts"][0]["candidate_artifact"]["generator_run_id"],
            ),
            "evaluator_run_id must differ",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_a_artifacts"][0][
                "scored_card"
            ].__setitem__("missing_fields", ["title"]),
            "missing_fields must be empty",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_b_artifacts"][0][
                "diverge_proof"
            ]["cell_statuses"].pop(
                next(iter(baseline["operator_b_artifacts"][0]["diverge_proof"]["cell_statuses"]))
            ),
            "full finance status universe",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_b_artifacts"][0][
                "diverge_proof"
            ]["cell_statuses"].__setitem__(
                baseline["operator_b_artifacts"][0]["diverge_proof"]["selected_target_cell"],
                "Sparse",
            ),
            "stay Missing",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_b_artifacts"][0][
                "diverge_proof"
            ].__setitem__("axioms", cast(Any, {})),
            "proof axioms are required",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_b_artifacts"][0][
                "diverge_proof"
            ]["axioms"].__setitem__(0, {"statement": "x"}),
            "target-bound axiom",
        ),
        (
            lambda results, baseline, e, blinded, audit: baseline["operator_b_artifacts"][0][
                "candidate_artifact"
            ].__setitem__(
                "target_cell_id", "mechanism=flow-driven|target=drawdown|horizon=intraday"
            ),
            "stored Operator B artifact target",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "source_idea_id", "missing"
            ),
            "source_idea_id",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "authorization_state", "approved"
            ),
            "stay report_only",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "runtime_authorized", True
            ),
            "runtime_authorized must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "evidence_sufficient", True
            ),
            "evidence_sufficient must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "component_ids", ["N11-FIN-01", "N11-FIN-99"]
            ),
            "component_ids must match",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "supporting_fact_ids", ["JEPA-FACT-01"]
            ),
            "supporting_fact_ids must match",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "co_occurrence_snapshot_id", "0" * 64
            ),
            "co_occurrence_snapshot_id must match",
        ),
        (
            lambda results, baseline, e, blinded, audit: e["candidates"][0].__setitem__(
                "artifact_hash", "0" * 64
            ),
            "artifact_hash does not match",
        ),
    ],
)
def test_operator_baselines_fail_closed_across_baseline_and_e_contracts(
    mutator, message: str
) -> None:
    results, baseline, e_candidates, blinded, audit = _pending_review_payloads()
    results = copy.deepcopy(results)
    baseline = copy.deepcopy(baseline)
    e_candidates = copy.deepcopy(e_candidates)
    blinded = copy.deepcopy(blinded)
    audit = copy.deepcopy(audit)
    mutator(results, baseline, e_candidates, blinded, audit)
    with pytest.raises(ValueError, match=message):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "packet_kind", "wrong"
            ),
            "packet_kind",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "authorization_state", "approved"
            ),
            "must be report_only",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "runtime_authorized", True
            ),
            "runtime_authorized must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "evidence_sufficient", True
            ),
            "evidence_sufficient must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "reviewer_identity", "llm"
            ),
            "human reviewer",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "human_usefulness_review_status", "done"
            ),
            "stay pending",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "items", blinded["items"][:-1]
            ),
            "exactly 9 items",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0].__setitem__(
                "item_index", 9
            ),
            "item_index must be sequential",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("abstention_reason", "insufficient_domain_context"),
            "abstention_reason must remain null",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("duplicate_group_id", "g1"),
            "duplicate_group_id must remain null",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("reviewer_notes", "x"),
            "reviewer_notes must remain null",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("possible_duplicate_of_blind_ids", ["BR-02"]),
            "possible_duplicate_of_blind_ids must stay empty",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][1].__setitem__(
                "blind_id", blinded["items"][0]["blind_id"]
            ),
            "blind_id values must be unique",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "packet_digest", "0" * 64
            ),
            "packet_digest does not match",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__("packet_kind", "wrong"),
            "packet_kind",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "authorization_state", "approved"
            ),
            "must be report_only",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "runtime_authorized", True
            ),
            "runtime_authorized must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "evidence_sufficient", True
            ),
            "evidence_sufficient must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "all_scores_null", False
            ),
            "all_scores_null true",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "review_packet_digest", "0" * 64
            ),
            "review_packet_digest must match",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "items", audit["items"][:-1]
            ),
            "exactly once",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit["items"][0].__setitem__(
                "item_index", 7
            ),
            "item_index must be sequential",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit["items"][0].__setitem__(
                "operator", "X"
            ),
            "operator does not match",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit["items"][0].__setitem__(
                "blind_sort_key", "0" * 64
            ),
            "blind_sort_key",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit["items"][1].__setitem__(
                "blind_id", audit["items"][0]["blind_id"]
            ),
            "blind_id values must be unique",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "manifest_digest", "0" * 64
            ),
            "manifest_digest does not match",
        ),
    ],
)
def test_operator_baselines_fail_closed_across_blind_and_audit_contracts(
    mutator, message: str
) -> None:
    results, baseline, e_candidates, blinded, audit = _pending_review_payloads()
    results = copy.deepcopy(results)
    baseline = copy.deepcopy(baseline)
    e_candidates = copy.deepcopy(e_candidates)
    blinded = copy.deepcopy(blinded)
    audit = copy.deepcopy(audit)
    mutator(results, baseline, e_candidates, blinded, audit)
    with pytest.raises(ValueError, match=message):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def _pending_review_payloads() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    results, baseline, e_candidates, blinded, audit = _payloads()
    blinded = copy.deepcopy(blinded)
    audit = copy.deepcopy(audit)
    blinded["reviewer_identity"] = "human_required"
    blinded["human_usefulness_review_status"] = "pending"
    blinded.pop("reviewed_at_utc", None)
    for item in blinded["items"]:
        form = item["review_form"]
        form["human_usefulness_score"] = None
        form["abstention_reason"] = None
        form["possible_duplicate_of_blind_ids"] = []
        form["duplicate_group_id"] = None
        form["duplicate_decision"] = None
        form["reviewer_notes"] = None
    blinded["packet_digest"] = opb.blinded_review_packet_digest(blinded)  # noqa: SLF001
    audit["reviewer_identity"] = "human_required"
    audit["human_usefulness_review_status"] = "pending"
    audit.pop("reviewed_at_utc", None)
    audit.pop("duplicate_rationale", None)
    audit["all_scores_null"] = True
    audit["review_packet_digest"] = blinded["packet_digest"]
    for item in audit["items"]:
        item["human_usefulness_score"] = None
        item["abstention_reason"] = None
        item["possible_duplicate_of_blind_ids"] = []
        item["duplicate_group_id"] = None
        item["duplicate_decision"] = None
        item["reviewer_notes"] = None
    audit["manifest_digest"] = opb.audit_manifest_digest(audit)  # noqa: SLF001
    return results, baseline, e_candidates, blinded, audit


def _completed_review_payloads() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    results, baseline, e_candidates, blinded, audit = _payloads()
    blinded = copy.deepcopy(blinded)
    audit = copy.deepcopy(audit)
    blinded["reviewer_identity"] = "human-reviewer"
    blinded["human_usefulness_review_status"] = "completed"
    blinded["reviewed_at_utc"] = "2026-09-02T15:50:20Z"
    audit["reviewer_identity"] = "human-reviewer"
    audit["human_usefulness_review_status"] = "completed"
    audit["reviewed_at_utc"] = "2026-09-02T15:50:20Z"
    audit["duplicate_rationale"] = "same idea, different targets"
    audit["all_scores_null"] = False
    scores = {
        "BR-01": 1,
        "BR-02": 2,
        "BR-03": 1,
        "BR-04": 2,
        "BR-05": 0,
        "BR-06": 1,
        "BR-07": 0,
        "BR-08": 0,
        "BR-09": 1,
    }
    duplicate_group = ["BR-05", "BR-07", "BR-08"]
    for item in blinded["items"]:
        blind_id = item["blind_id"]
        form = item["review_form"]
        form["human_usefulness_score"] = scores[blind_id]
        form["abstention_reason"] = None
        form["reviewer_notes"] = None
        if blind_id in duplicate_group:
            form["duplicate_group_id"] = "DG-01"
            form["duplicate_decision"] = "collapse_same_idea_variants"
            form["possible_duplicate_of_blind_ids"] = [
                candidate for candidate in duplicate_group if candidate != blind_id
            ]
        else:
            form["duplicate_group_id"] = None
            form["duplicate_decision"] = "distinct"
            form["possible_duplicate_of_blind_ids"] = []
    for item in audit["items"]:
        blind_id = item["blind_id"]
        item["human_usefulness_score"] = scores[blind_id]
        item["abstention_reason"] = None
        item["reviewer_notes"] = None
        if blind_id in duplicate_group:
            item["duplicate_group_id"] = "DG-01"
            item["duplicate_decision"] = "collapse_same_idea_variants"
            item["possible_duplicate_of_blind_ids"] = [
                candidate for candidate in duplicate_group if candidate != blind_id
            ]
        else:
            item["duplicate_group_id"] = None
            item["duplicate_decision"] = "distinct"
            item["possible_duplicate_of_blind_ids"] = []
    blinded["packet_digest"] = opb.blinded_review_packet_digest(blinded)  # noqa: SLF001
    audit["review_packet_digest"] = blinded["packet_digest"]
    audit["manifest_digest"] = opb.audit_manifest_digest(audit)  # noqa: SLF001
    return results, baseline, e_candidates, blinded, audit


def test_completed_human_review_is_validated_and_metrics_are_recomputed() -> None:
    results, baseline, e_candidates, blinded, audit = _completed_review_payloads()
    summary = evaluate_matched_count_operator_baselines(
        results["proposed_ideas"],
        extracted_facts=results["extracted_facts"],
        baseline_execution=baseline,
        operator_e_candidates=e_candidates["candidates"],
        blinded_review_packet=blinded,
        audit_manifest=audit,
    )
    assert summary["usefulness_review_status"] == "completed_human_review"
    assert summary["reviewed_usefulness_at_matched_candidate_count"] == {
        "raw_mean": pytest.approx(8 / 9, abs=1e-6),
        "duplicate_collapsed_mean": pytest.approx(8 / 7, abs=1e-6),
    }
    metrics = summary["human_usefulness_review"]
    assert metrics["reviewer_identity"] == "human-reviewer"
    assert metrics["reviewed_at_utc"] == "2026-09-02T15:50:20Z"
    assert metrics["descriptive_only"] is True
    assert metrics["statistical_significance_inference"] is False
    assert metrics["duplicate_rationale"] == "same idea, different targets"
    assert metrics["raw"] == {
        "item_count": 9,
        "scored_item_count": 9,
        "abstention_count": 0,
        "total_score": 8,
        "mean_score": pytest.approx(8 / 9, abs=1e-6),
    }
    assert metrics["duplicate_collapsed"] == {
        "effective_item_count": 7,
        "scored_item_count": 7,
        "abstention_count": 0,
        "total_score": 8,
        "mean_score": pytest.approx(8 / 7, abs=1e-6),
    }
    assert metrics["by_operator"] == {
        "A": {
            "raw_scores": [2, 2, 1],
            "collapsed_scores": [2, 2, 1],
            "mean_score": pytest.approx(5 / 3, abs=1e-6),
        },
        "B": {"raw_scores": [0, 0, 0], "collapsed_scores": [0], "mean_score": 0.0},
        "E": {"raw_scores": [1, 1, 1], "collapsed_scores": [1, 1, 1], "mean_score": 1.0},
    }


def test_completed_human_review_allows_packet_declared_abstention_vocabulary() -> None:
    results, baseline, e_candidates, blinded, audit = _completed_review_payloads()
    declared_abstention = "needs_expert_review"
    blinded["abstention_reasons"].append(declared_abstention)
    blinded["items"][0]["review_form"]["human_usefulness_score"] = None
    blinded["items"][0]["review_form"]["abstention_reason"] = declared_abstention
    audit["items"][0]["human_usefulness_score"] = None
    audit["items"][0]["abstention_reason"] = declared_abstention
    blinded["packet_digest"] = opb.blinded_review_packet_digest(blinded)  # noqa: SLF001
    audit["review_packet_digest"] = blinded["packet_digest"]
    audit["manifest_digest"] = opb.audit_manifest_digest(audit)  # noqa: SLF001

    summary = evaluate_matched_count_operator_baselines(
        results["proposed_ideas"],
        extracted_facts=results["extracted_facts"],
        baseline_execution=baseline,
        operator_e_candidates=e_candidates["candidates"],
        blinded_review_packet=blinded,
        audit_manifest=audit,
    )
    metrics = summary["human_usefulness_review"]
    assert summary["usefulness_review_status"] == "completed_human_review"
    assert metrics["reviewed_at_utc"] == "2026-09-02T15:50:20Z"
    assert metrics["raw"] == {
        "item_count": 9,
        "scored_item_count": 8,
        "abstention_count": 1,
        "total_score": 7,
        "mean_score": pytest.approx(7 / 8, abs=1e-6),
    }
    assert metrics["duplicate_collapsed"] == {
        "effective_item_count": 7,
        "scored_item_count": 6,
        "abstention_count": 1,
        "total_score": 7,
        "mean_score": pytest.approx(7 / 6, abs=1e-6),
    }
    assert metrics["raw"]["abstention_count"] == 1
    assert metrics["duplicate_collapsed"]["abstention_count"] == 1

    undeclared = copy.deepcopy(audit)
    undeclared["items"][1]["human_usefulness_score"] = None
    undeclared["items"][1]["abstention_reason"] = "not_declared"
    undeclared["manifest_digest"] = opb.audit_manifest_digest(undeclared)  # noqa: SLF001
    with pytest.raises(ValueError, match="abstention_reason"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=undeclared,
        )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("human_usefulness_score", None),
            "human_usefulness_score",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("human_usefulness_score", True),
            "0..3",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("human_usefulness_score", 4),
            "0..3",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("abstention_reason", "insufficient_domain_context"),
            "exclusive",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][0][
                "review_form"
            ].__setitem__("abstention_reason", "bad_reason"),
            "abstention_reason",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "reviewer_identity", "human_required"
            ),
            "reviewer_identity",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "reviewed_at_utc", "2026-09-02T15:50:20"
            ),
            "UTC",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][4][
                "review_form"
            ].__setitem__("duplicate_group_id", None),
            "duplicate_group_id",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][4][
                "review_form"
            ].__setitem__("possible_duplicate_of_blind_ids", ["BR-07"]),
            "possible_duplicate_of_blind_ids",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][4][
                "review_form"
            ].__setitem__("duplicate_decision", "bad"),
            "duplicate_decision",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded["items"][4][
                "review_form"
            ].__setitem__("duplicate_group_id", "DG-02"),
            "singleton|asymmetric",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit["items"][0].__setitem__(
                "human_usefulness_score", 3
            ),
            "packet/audit",
        ),
        (
            lambda results, baseline, e, blinded, audit: audit.__setitem__(
                "manifest_digest", "0" * 64
            ),
            "manifest_digest",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "runtime_authorized", True
            ),
            "runtime_authorized must be false",
        ),
        (
            lambda results, baseline, e, blinded, audit: blinded.__setitem__(
                "evidence_sufficient", True
            ),
            "evidence_sufficient must be false",
        ),
    ],
)
def test_completed_human_review_rejects_invalid_state_transitions(mutator, message: str) -> None:
    results, baseline, e_candidates, blinded, audit = _completed_review_payloads()
    mutator(results, baseline, e_candidates, blinded, audit)
    if blinded.get("packet_digest"):
        blinded["packet_digest"] = opb.blinded_review_packet_digest(blinded)  # noqa: SLF001
    if audit.get("review_packet_digest") is not None:
        audit["review_packet_digest"] = blinded["packet_digest"]
    if audit.get("manifest_digest") and message != "manifest_digest":
        audit["manifest_digest"] = opb.audit_manifest_digest(audit)  # noqa: SLF001
    with pytest.raises(ValueError, match=message):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_completed_human_review_supports_valid_abstention_and_recomputes_metrics() -> None:
    results, baseline, e_candidates, blinded, audit = _completed_review_payloads()
    blinded["items"][0]["review_form"]["human_usefulness_score"] = None
    blinded["items"][0]["review_form"]["abstention_reason"] = "unclear_claim"
    audit["items"][0]["human_usefulness_score"] = None
    audit["items"][0]["abstention_reason"] = "unclear_claim"
    blinded["packet_digest"] = opb.blinded_review_packet_digest(blinded)  # noqa: SLF001
    audit["review_packet_digest"] = blinded["packet_digest"]
    audit["manifest_digest"] = opb.audit_manifest_digest(audit)  # noqa: SLF001

    summary = evaluate_matched_count_operator_baselines(
        results["proposed_ideas"],
        extracted_facts=results["extracted_facts"],
        baseline_execution=baseline,
        operator_e_candidates=e_candidates["candidates"],
        blinded_review_packet=blinded,
        audit_manifest=audit,
    )
    metrics = summary["human_usefulness_review"]
    assert metrics["raw"] == {
        "item_count": 9,
        "scored_item_count": 8,
        "abstention_count": 1,
        "total_score": 7,
        "mean_score": pytest.approx(7 / 8, abs=1e-6),
    }
    assert metrics["duplicate_collapsed"] == {
        "effective_item_count": 7,
        "scored_item_count": 6,
        "abstention_count": 1,
        "total_score": 7,
        "mean_score": pytest.approx(7 / 6, abs=1e-6),
    }


def test_completed_human_review_duplicate_groups_handle_mixed_and_all_abstained_members() -> None:
    results, baseline, e_candidates, blinded, audit = _completed_review_payloads()
    for blind_id in ("BR-07", "BR-08"):
        for item in blinded["items"]:
            if item["blind_id"] == blind_id:
                item["review_form"]["human_usefulness_score"] = None
                item["review_form"]["abstention_reason"] = "possible_duplicate"
        for item in audit["items"]:
            if item["blind_id"] == blind_id:
                item["human_usefulness_score"] = None
                item["abstention_reason"] = "possible_duplicate"
    blinded["packet_digest"] = opb.blinded_review_packet_digest(blinded)  # noqa: SLF001
    audit["review_packet_digest"] = blinded["packet_digest"]
    audit["manifest_digest"] = opb.audit_manifest_digest(audit)  # noqa: SLF001
    summary = evaluate_matched_count_operator_baselines(
        results["proposed_ideas"],
        extracted_facts=results["extracted_facts"],
        baseline_execution=baseline,
        operator_e_candidates=e_candidates["candidates"],
        blinded_review_packet=blinded,
        audit_manifest=audit,
    )
    metrics = summary["human_usefulness_review"]
    assert metrics["duplicate_collapsed"] == {
        "effective_item_count": 7,
        "scored_item_count": 7,
        "abstention_count": 0,
        "total_score": 8,
        "mean_score": pytest.approx(8 / 7, abs=1e-6),
    }
    assert metrics["by_operator"]["B"]["collapsed_scores"] == [0.0]

    all_abstained = _completed_review_payloads()
    results2, baseline2, e_candidates2, blinded2, audit2 = all_abstained
    for blind_id in ("BR-05", "BR-07", "BR-08"):
        for item in blinded2["items"]:
            if item["blind_id"] == blind_id:
                item["review_form"]["human_usefulness_score"] = None
                item["review_form"]["abstention_reason"] = "possible_duplicate"
        for item in audit2["items"]:
            if item["blind_id"] == blind_id:
                item["human_usefulness_score"] = None
                item["abstention_reason"] = "possible_duplicate"
    blinded2["packet_digest"] = opb.blinded_review_packet_digest(blinded2)  # noqa: SLF001
    audit2["review_packet_digest"] = blinded2["packet_digest"]
    audit2["manifest_digest"] = opb.audit_manifest_digest(audit2)  # noqa: SLF001
    summary2 = evaluate_matched_count_operator_baselines(
        results2["proposed_ideas"],
        extracted_facts=results2["extracted_facts"],
        baseline_execution=baseline2,
        operator_e_candidates=e_candidates2["candidates"],
        blinded_review_packet=blinded2,
        audit_manifest=audit2,
    )
    metrics2 = summary2["human_usefulness_review"]
    assert metrics2["duplicate_collapsed"] == {
        "effective_item_count": 7,
        "scored_item_count": 6,
        "abstention_count": 1,
        "total_score": 8,
        "mean_score": pytest.approx(8 / 6, abs=1e-6),
    }
    assert metrics2["by_operator"]["B"]["collapsed_scores"] == []
    assert metrics2["by_operator"]["B"]["mean_score"] is None


def test_real_baseline_cards_require_human_dval_and_are_rejected_without_it() -> None:
    baseline = _json("baseline-evidence.json")
    for row in [*baseline["operator_a_artifacts"], *baseline["operator_b_artifacts"]]:
        candidate = row["candidate_artifact"]["candidate"]
        card = row["scored_card"]
        novelty = row["candidate_artifact"]["novelty"]
        assert "dval" not in candidate or score_dval(candidate) == 0
        computed_nov = apply_novelty_threshold(
            novelty_term(
                evidence=row["grounding"]["evidence"],
                snapshot_state=row["grounding"]["snapshot_state"],
                grounding_class=row["grounding"]["grounding_class"],
            ),
            evidence=row["grounding"]["evidence"],
            tau=NOVELTY_THRESHOLD_TAU,
        )
        computed_mech = score_mech(candidate, domain_pack="finance/1")
        computed_fals = score_fals(candidate)
        computed_dpred = score_dpred(candidate)
        computed_dval = score_dval(candidate)
        computed_viability = viability(
            nov=computed_nov,
            mech=computed_mech,
            fals=computed_fals,
            dpred=computed_dpred,
            dval=computed_dval,
        )
        assert novelty["tau"] == NOVELTY_THRESHOLD_TAU
        assert novelty["tau_semantics"] == NOVELTY_TAU_SEMANTICS
        assert card["nov"] == computed_nov
        assert card["mech"] == computed_mech
        assert card["fals"] == computed_fals
        assert card["dpred"] == computed_dpred
        assert card["dval"] == computed_dval == 0
        assert card["viability"] == computed_viability == 0
        assert card["card_decision"] == card_decision(0) == "rejected"
        assert card["missing_fields"] == missing_card_fields(card) == []


def test_real_baseline_embedding_records_full_immutable_ollama_digest() -> None:
    baseline = _json("baseline-evidence.json")
    model = baseline["embedding_model"]
    assert model["model_name"] == "qwen3-embedding:latest"
    assert model["installed_model_digest"] == (
        "64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b"
    )
    assert len(model["installed_model_digest"]) == 64
    assert model["model_blob_sha256"] == (
        "3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85"
    )


def test_validator_recomputes_grounding_measurement_and_score_fields() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()
    row = baseline["operator_a_artifacts"][0]
    candidate = row["candidate_artifact"]["candidate"]
    grounding = row["grounding"]
    novelty = row["candidate_artifact"]["novelty"]
    card = row["scored_card"]
    distances = [item["distance"] for item in grounding["neighbors"]]
    assert grounding["measurement_artifact_digest"] == tau_measurement_artifact_digest(grounding)
    assert grounding["candidate"]["paraphrase"] == normalize_paraphrase(candidate["paraphrase"])
    assert (
        grounding["candidate"]["text_digest"]
        == row["candidate_artifact"]["grounding"]["candidate"]["text_digest"]
    )
    assert len(grounding["neighbors"]) == 5
    assert [item["rank"] for item in grounding["neighbors"]] == [1, 2, 3, 4, 5]
    assert len({item["record_id"] for item in grounding["neighbors"]}) == 5
    assert grounding["measurement"]["distances"] == distances
    assert grounding["measurement"]["evidence_mean_distance"] == pytest.approx(sum(distances) / 5)
    assert all(
        canonical_reviewed_projection_digest(item["reviewed_projection"])
        == item["reviewed_projection_digest"]
        for item in grounding["neighbors"]
    )
    assert novelty["measurement_stamp"] == grounding["measurement_stamp"]
    assert card["title"] == candidate["title"]
    assert card["cell_id"] == (
        "mechanism=behavioral|target=returns|horizon=daily"
        if card["generating_operator"] == "A"
        else card["cell_id"]
    )

    tampered_measurement = copy.deepcopy(baseline)
    tampered_measurement["operator_a_artifacts"][0]["grounding"]["measurement"]["distances"][0] = (
        0.99
    )
    tampered_measurement["operator_a_artifacts"][0]["candidate_artifact"]["grounding"][
        "measurement"
    ]["distances"][0] = 0.99
    with pytest.raises(ValueError, match="measurement artifact digest"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=tampered_measurement,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    tampered_score = copy.deepcopy(baseline)
    tampered_score["operator_a_artifacts"][0]["scored_card"]["dval"] = 3
    with pytest.raises(ValueError, match="scored card dval"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=tampered_score,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_validator_rejects_duplicate_ids_hashes_and_incomplete_audit_coverage() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()

    duplicated_ids = copy.deepcopy(baseline)
    duplicated_ids["operator_b_artifacts"][0]["candidate_id"] = duplicated_ids[
        "operator_a_artifacts"
    ][0]["candidate_id"]
    with pytest.raises(ValueError, match="candidate ids must be unique"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=duplicated_ids,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    duplicated_hashes = copy.deepcopy(e_candidates)
    duplicated_hashes["candidates"][0] = copy.deepcopy(duplicated_hashes["candidates"][1])
    duplicated_hashes["candidates"][0]["artifact_id"] = "E-REPORT-01"
    with pytest.raises(ValueError, match="artifact hashes must be unique"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=duplicated_hashes["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    missing_audit = copy.deepcopy(audit)
    missing_audit["items"] = missing_audit["items"][:-1]
    with pytest.raises(ValueError, match="exactly once"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=missing_audit,
        )

    duplicate_audit = copy.deepcopy(audit)
    duplicate_audit["items"][-1] = copy.deepcopy(duplicate_audit["items"][-2])
    duplicate_audit["items"][-1]["blind_id"] = "BR-09"
    duplicate_audit["items"][-1]["item_index"] = 9
    with pytest.raises(ValueError, match="exactly once"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=duplicate_audit,
        )


def test_operator_baselines_reject_bad_a_fact_and_b_editorial_bindings() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()

    with pytest.raises(ValueError, match="extracted_facts is required"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=cast(Any, object()),
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    bad_binding = copy.deepcopy(baseline)
    bad_binding["operator_a_artifacts"][0]["source_record_id"] = "N11-FIN-02"
    with pytest.raises(ValueError, match="source_fact_id/source_record_id binding"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=bad_binding,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    duplicate_fact_ids = copy.deepcopy(baseline)
    duplicate_fact_ids["operator_a_artifacts"][1]["source_fact_id"] = duplicate_fact_ids[
        "operator_a_artifacts"
    ][0]["source_fact_id"]
    duplicate_fact_ids["operator_a_artifacts"][1]["source_record_id"] = duplicate_fact_ids[
        "operator_a_artifacts"
    ][0]["source_record_id"]
    with pytest.raises(ValueError, match="source_fact_id values must be unique"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=duplicate_fact_ids,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    identical_inversion = copy.deepcopy(baseline)
    source_fact_id = identical_inversion["operator_a_artifacts"][0]["source_fact_id"]
    source_claim = next(
        row["claim"] for row in results["extracted_facts"] if row["fact_id"] == source_fact_id
    )
    identical_inversion["operator_a_artifacts"][0]["inverted_axiom"] = source_claim
    with pytest.raises(ValueError, match="inverted_axiom must differ"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=identical_inversion,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    bad_assumed_status = copy.deepcopy(baseline)
    bad_assumed_status["operator_b_artifacts"][0]["assumed_status"] = "Sparse"
    with pytest.raises(ValueError, match="assumed_status must be Missing"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=bad_assumed_status,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    bad_cell_id = copy.deepcopy(baseline)
    bad_cell_id["operator_b_artifacts"][0]["cell_id"] = (
        "mechanism=flow-driven|target=drawdown|horizon=intraday"
    )
    with pytest.raises(ValueError, match="row cell_id must match the selected target"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=bad_cell_id,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_operator_baselines_require_exact_approved_source_manifests() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()

    swapped = copy.deepcopy(baseline)
    swapped["source_manifests"] = list(reversed(swapped["source_manifests"]))
    with pytest.raises(ValueError, match="approved root"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=swapped,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    traversed = copy.deepcopy(baseline)
    traversed["source_manifests"][0]["manifest_path"] = (
        "docs/reviews/nsqd-projection-review-2026-08-28/final/../final/manifest.toml"
    )
    with pytest.raises(ValueError, match="approved root"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=traversed,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    arbitrary_file = copy.deepcopy(baseline)
    arbitrary_file["source_manifests"][0]["manifest_path"] = "pyproject.toml"
    arbitrary_file["source_manifests"][0]["sha256"] = hashlib.sha256(
        (REPO_ROOT / "pyproject.toml").read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="approved root"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=arbitrary_file,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_operator_baselines_reject_additional_source_manifest_integrity_drift() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()

    missing_one = copy.deepcopy(baseline)
    missing_one["source_manifests"] = missing_one["source_manifests"][:1]
    with pytest.raises(ValueError, match="source_manifests"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=missing_one,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    duplicate_paths = copy.deepcopy(baseline)
    duplicate_paths["source_manifests"][1]["manifest_path"] = duplicate_paths["source_manifests"][
        0
    ]["manifest_path"]
    duplicate_paths["source_manifests"][1]["sha256"] = duplicate_paths["source_manifests"][0][
        "sha256"
    ]
    with pytest.raises(ValueError, match="approved root|must be unique"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=duplicate_paths,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    hash_drift = copy.deepcopy(baseline)
    hash_drift["source_manifests"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest sha256"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=hash_drift,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_operator_baselines_reject_projection_binding_identity_drift() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()

    for field, value, message in [
        ("projection_path", "pyproject.toml", "projection_path is outside the approved root"),
        ("approved_excerpt", "pyproject.toml", "approved_excerpt is outside the approved root"),
        ("title", "Wrong title", "title does not match projection file"),
        (
            "source_paper_id",
            "doi:wrong",
            "source_paper_id does not match projection file",
        ),
        (
            "approved_record_id",
            "NOT-APPROVED",
            "not supported by the finance packet",
        ),
    ]:
        mutated = copy.deepcopy(baseline)
        mutated["projection_bindings"][0][field] = value
        with pytest.raises(ValueError, match=message):
            evaluate_matched_count_operator_baselines(
                results["proposed_ideas"],
                extracted_facts=results["extracted_facts"],
                baseline_execution=mutated,
                operator_e_candidates=e_candidates["candidates"],
                blinded_review_packet=blinded,
                audit_manifest=audit,
            )


def test_private_runtime_and_audit_helpers_reject_missing_paths_sort_drift_and_bad_scalars(
    tmp_path: Path,
) -> None:
    _results, baseline, e_candidates, blinded, audit = _pending_review_payloads()
    with pytest.raises(ValueError, match="db_path is missing"):
        opb.verify_scratch_execution_receipt(
            baseline["execution_receipt"],
            scratch_runtime={
                "db_path": str(tmp_path / "nsqd-jepa-baselines-missing" / "nsqd.sqlite"),
                "index_path": str(tmp_path / "nsqd-jepa-baselines-missing" / "index"),
                "no_production_writes": True,
                "production_write_paths": [],
            },
        )
    scratch = tmp_path / "nsqd-jepa-baselines-local"
    scratch.mkdir()
    db_path = scratch / "nsqd.sqlite"
    db_path.write_bytes(b"db")
    with pytest.raises(ValueError, match="index_path is missing"):
        opb.verify_scratch_execution_receipt(
            baseline["execution_receipt"],
            scratch_runtime={
                "db_path": str(db_path),
                "index_path": str(scratch / "index"),
                "no_production_writes": True,
                "production_write_paths": [],
            },
        )

    known_hashes = {
        row["candidate_artifact_hash"]: row["candidate_artifact"]["operator"]
        for row in [*baseline["operator_a_artifacts"], *baseline["operator_b_artifacts"]]
    }
    known_hashes.update({row["artifact_hash"]: "E" for row in e_candidates["candidates"]})
    mutated = copy.deepcopy(audit)
    mutated["items"] = sorted(
        mutated["items"], key=lambda item: item["blind_sort_key"], reverse=True
    )
    for index, item in enumerate(mutated["items"], start=1):
        item["item_index"] = index
    with pytest.raises(ValueError, match="sorted by blind_sort_key"):
        opb._require_audit_manifest(  # noqa: SLF001
            mutated,
            review_packet=opb._require_blinded_review_packet(blinded, expected_item_count=9),  # noqa: SLF001
            known_hashes=known_hashes,
        )

    with pytest.raises(ValueError, match="non-negative integer"):
        opb._required_nonnegative_int({"count": -1}, "count")  # noqa: SLF001
    with pytest.raises(ValueError, match="non-negative integer"):
        opb._required_nonnegative_int({"count": True}, "count")  # noqa: SLF001


def test_private_manifest_and_extracted_fact_parsers_fail_closed() -> None:
    with pytest.raises(ValueError, match="manifest_path is missing"):
        opb._load_manifest_fixture_row(
            Path("/definitely/missing.toml"), approved_record_id="N11-FIN-01"
        )  # noqa: SLF001
    with pytest.raises(ValueError, match="extracted_facts must be extracted_fact rows"):
        opb._require_extracted_facts([{"result_class": "proposed_idea"}])  # noqa: SLF001


def test_baseline_execution_receipt_binds_runtime_store_and_index() -> None:
    baseline = _json("baseline-evidence.json")
    receipt = baseline["execution_receipt"]
    assert receipt["candidate_count"] == 6
    assert receipt["card_count"] == 6
    assert len(receipt["candidate_artifact_hashes"]) == 6
    assert len(receipt["frontier_card_hashes"]) == 6
    assert receipt["sqlite_sha256"]
    assert receipt["lancedb_tree_sha256"]


def test_private_execution_receipt_and_binding_guards_cover_runtime_edges() -> None:
    _results, baseline, _e_candidates, _blinded, _audit = _payloads()

    with pytest.raises(ValueError, match="sqlite_sha256"):
        bad_receipt = copy.deepcopy(baseline["execution_receipt"])
        bad_receipt["sqlite_sha256"] = "0" * 64
        opb.verify_scratch_execution_receipt(
            bad_receipt,
            scratch_runtime=baseline["scratch_runtime"],
        )

    with pytest.raises(ValueError, match="lancedb_tree_sha256"):
        bad_receipt = copy.deepcopy(baseline["execution_receipt"])
        bad_receipt["lancedb_tree_sha256"] = "0" * 64
        opb.verify_scratch_execution_receipt(
            bad_receipt,
            scratch_runtime=baseline["scratch_runtime"],
        )

    with pytest.raises(ValueError, match="candidate_count"):
        bad_receipt = copy.deepcopy(baseline["execution_receipt"])
        bad_receipt["candidate_count"] = 5
        opb.verify_scratch_execution_receipt(
            bad_receipt,
            scratch_runtime=baseline["scratch_runtime"],
        )

    with pytest.raises(ValueError, match="frontier card payload sha"):
        bad_receipt = copy.deepcopy(baseline["execution_receipt"])
        first = bad_receipt["frontier_card_hashes"][0]
        bad_receipt["frontier_card_payload_sha256"][first] = "0" * 64
        opb.verify_scratch_execution_receipt(
            bad_receipt,
            scratch_runtime=baseline["scratch_runtime"],
        )

    with pytest.raises(ValueError, match="projected_record_id"):
        bad_bindings = copy.deepcopy(baseline["projection_bindings"])
        bad_bindings[0]["projected_record_id"] = "0" * 64
        opb._require_projection_bindings(bad_bindings)  # noqa: SLF001

    with pytest.raises(ValueError, match="reviewed_projection_digest"):
        bad_bindings = copy.deepcopy(baseline["projection_bindings"])
        bad_bindings[0]["reviewed_projection_digest"] = "0" * 64
        opb._require_projection_bindings(bad_bindings)  # noqa: SLF001


def test_private_grounding_and_novelty_guards_recompute_runtime_contracts() -> None:
    _results, baseline, _e_candidates, _blinded, _audit = _payloads()
    row = baseline["operator_a_artifacts"][0]
    candidate = row["candidate_artifact"]["candidate"]
    grounding = row["grounding"]
    projected = opb._require_projection_bindings(baseline["projection_bindings"])  # noqa: SLF001

    with pytest.raises(ValueError, match="closest_prior_art"):
        bad_grounding = copy.deepcopy(grounding)
        bad_grounding["closest_prior_art"]["record_id"] = "missing"
        opb._require_grounding(  # noqa: SLF001
            bad_grounding,
            candidate=candidate,
            artifact_hash=row["candidate_artifact_hash"],
            approved_projection_digests=projected["approved_projection_digests"],
            projected_bindings=projected["by_projected_record_id"],
        )

    with pytest.raises(ValueError, match="approved projection record"):
        projected_bindings = cast(dict[str, dict[str, Any]], projected["by_projected_record_id"])
        bad_projected = {str(key): value for key, value in projected_bindings.items()}
        bad_projected.pop(grounding["neighbors"][0]["record_id"])
        opb._require_grounding(  # noqa: SLF001
            grounding,
            candidate=candidate,
            artifact_hash=row["candidate_artifact_hash"],
            approved_projection_digests=projected["approved_projection_digests"],
            projected_bindings=bad_projected,
        )

    with pytest.raises(ValueError, match="novelty evidence"):
        bad_novelty = copy.deepcopy(row["candidate_artifact"]["novelty"])
        bad_novelty["evidence"] = 0.0
        opb._require_novelty(bad_novelty, grounding=grounding)  # noqa: SLF001

    with pytest.raises(ValueError, match="tau_semantics"):
        bad_novelty = copy.deepcopy(row["candidate_artifact"]["novelty"])
        bad_novelty["tau_semantics"] = "wrong"
        opb._require_novelty(bad_novelty, grounding=grounding)  # noqa: SLF001

    with pytest.raises(ValueError, match="measurement_stamp"):
        bad_novelty = copy.deepcopy(row["candidate_artifact"]["novelty"])
        bad_novelty["measurement_stamp"] = {}
        opb._require_novelty(bad_novelty, grounding=grounding)  # noqa: SLF001

    assert opb._optional_float(None, field="grounding.evidence") is None  # noqa: SLF001
    with pytest.raises(ValueError, match="numeric or null"):
        opb._optional_float("nan", field="grounding.evidence")  # noqa: SLF001
    with pytest.raises(ValueError, match="grounding_class is invalid"):
        opb._required_grounding_class("bad")  # noqa: SLF001


def test_private_tree_digest_and_runtime_json_helpers_are_deterministic(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_text("a", encoding="utf-8")
    nested = tree / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("b", encoding="utf-8")
    digest = opb.lancedb_tree_digest(tree)
    assert len(digest) == 64
    assert digest == opb.lancedb_tree_digest(tree)

    with pytest.raises(ValueError, match="empty"):
        empty = tmp_path / "empty"
        empty.mkdir()
        opb.lancedb_tree_digest(empty)

    assert opb._json_mapping('{"a":1}')["a"] == 1  # noqa: SLF001
    with pytest.raises(ValueError, match="JSON object"):
        opb._json_mapping("[1,2,3]")  # noqa: SLF001


def test_private_helper_guards_cover_scored_card_and_grounding_fail_closed_paths() -> None:
    _results, baseline, _e_candidates, _blinded, _audit = _payloads()
    row = baseline["operator_a_artifacts"][0]
    candidate = row["candidate_artifact"]["candidate"]
    grounding = row["grounding"]
    card = row["scored_card"]
    projected = opb._require_projection_bindings(baseline["projection_bindings"])  # noqa: SLF001

    for field, value, message in [
        ("card_id", "0" * 64, "bind the candidate_artifact_hash"),
        ("generating_operator", "B", "generating_operator"),
        ("domain_policy_id", "optimization/1", "stay in finance/1"),
        ("cell_id", "mechanism=flow-driven|target=drawdown|horizon=intraday", "cell_id"),
        ("archive_cell_key", "bad", "archive_cell_key"),
        ("snapshot_id", "0" * 64, "snapshot_id"),
        ("corpus_version", 999, "corpus_version"),
        ("evaluator_run_id", row["candidate_artifact"]["generator_run_id"], "evaluator_run_id"),
        ("generator_run_id", "other", "generator_run_id"),
    ]:
        mutated = copy.deepcopy(card)
        mutated[field] = value
        with pytest.raises(ValueError, match=message):
            opb._require_scored_card(  # noqa: SLF001
                mutated,
                artifact_hash=row["candidate_artifact_hash"],
                operator="A",
                generator_run_id=row["candidate_artifact"]["generator_run_id"],
                candidate=candidate,
                grounding=grounding,
            )

    mutated = copy.deepcopy(card)
    mutated["missing_fields"] = ["title"]
    with pytest.raises(ValueError, match="missing_fields"):
        opb._require_scored_card(  # noqa: SLF001
            mutated,
            artifact_hash=row["candidate_artifact_hash"],
            operator="A",
            generator_run_id=row["candidate_artifact"]["generator_run_id"],
            candidate=candidate,
            grounding=grounding,
        )

    for field, value, message in [
        ("candidate_artifact_hash", "0" * 64, "candidate_artifact_hash"),
        ("snapshot_id", "0" * 64, "snapshot_id"),
        ("snapshot_digest", "0" * 64, "snapshot_digest"),
        ("corpus_version", 999, "corpus_version"),
        ("snapshot_state", "calibration", "snapshot_state"),
        ("pair_id", "0" * 64, "pair_id"),
    ]:
        mutated = copy.deepcopy(grounding)
        mutated[field] = value
        with pytest.raises(ValueError, match=message):
            opb._require_grounding(  # noqa: SLF001
                mutated,
                candidate=candidate,
                artifact_hash=row["candidate_artifact_hash"],
                approved_projection_digests=projected["approved_projection_digests"],
                projected_bindings=projected["by_projected_record_id"],
            )

    mutated = copy.deepcopy(grounding)
    mutated["candidate"]["artifact_hash"] = "0" * 64
    with pytest.raises(ValueError, match="candidate artifact_hash"):
        opb._require_grounding(  # noqa: SLF001
            mutated,
            candidate=candidate,
            artifact_hash=row["candidate_artifact_hash"],
            approved_projection_digests=projected["approved_projection_digests"],
            projected_bindings=projected["by_projected_record_id"],
        )

    mutated = copy.deepcopy(grounding)
    mutated["candidate"]["paraphrase"] = "wrong"
    with pytest.raises(ValueError, match="candidate paraphrase"):
        opb._require_grounding(  # noqa: SLF001
            mutated,
            candidate=candidate,
            artifact_hash=row["candidate_artifact_hash"],
            approved_projection_digests=projected["approved_projection_digests"],
            projected_bindings=projected["by_projected_record_id"],
        )

    mutated = copy.deepcopy(grounding)
    mutated["candidate"]["text_digest"] = "0" * 64
    with pytest.raises(ValueError, match="text_digest"):
        opb._require_grounding(  # noqa: SLF001
            mutated,
            candidate=candidate,
            artifact_hash=row["candidate_artifact_hash"],
            approved_projection_digests=projected["approved_projection_digests"],
            projected_bindings=projected["by_projected_record_id"],
        )


def test_private_helper_guards_cover_blind_audit_and_scalar_parsers(tmp_path: Path) -> None:
    _results, baseline, e_candidates, blinded, audit = _pending_review_payloads()
    known_hashes = {
        row["candidate_artifact_hash"]: row["candidate_artifact"]["operator"]
        for row in [*baseline["operator_a_artifacts"], *baseline["operator_b_artifacts"]]
    }
    known_hashes.update({row["artifact_hash"]: "E" for row in e_candidates["candidates"]})

    for field, value, message in [
        ("blinding_scope", "family-proof", "operator-label blinding"),
        ("blinding_limitation", "none", "blinding limitation"),
    ]:
        mutated = copy.deepcopy(blinded)
        mutated[field] = value
        with pytest.raises(ValueError, match=message):
            opb._require_blinded_review_packet(mutated, expected_item_count=9)  # noqa: SLF001

    mutated = copy.deepcopy(blinded)
    mutated["items"][0]["review_form"]["human_usefulness_score"] = 1
    with pytest.raises(ValueError, match="human_usefulness_score"):
        opb._require_blinded_review_packet(mutated, expected_item_count=9)  # noqa: SLF001

    mutated = copy.deepcopy(blinded)
    mutated["items"][0]["review_form"]["duplicate_decision"] = "duplicate"
    with pytest.raises(ValueError, match="duplicate_decision"):
        opb._require_blinded_review_packet(mutated, expected_item_count=9)  # noqa: SLF001

    mutated = copy.deepcopy(audit)
    mutated["items"][0]["artifact_hash"] = "0" * 64
    with pytest.raises(ValueError, match="known artifact hash"):
        opb._require_audit_manifest(  # noqa: SLF001
            mutated,
            review_packet=opb._require_blinded_review_packet(blinded, expected_item_count=9),  # noqa: SLF001
            known_hashes=known_hashes,
        )

    mutated = copy.deepcopy(audit)
    mutated["items"][0]["item_index"] = 7
    with pytest.raises(ValueError, match="item_index"):
        opb._require_audit_manifest(  # noqa: SLF001
            mutated,
            review_packet=opb._require_blinded_review_packet(blinded, expected_item_count=9),  # noqa: SLF001
            known_hashes=known_hashes,
        )

    mutated = copy.deepcopy(audit)
    mutated["items"][0]["blind_id"] = mutated["items"][1]["blind_id"]
    with pytest.raises(ValueError, match="blind_id values must be unique"):
        opb._require_audit_manifest(  # noqa: SLF001
            mutated,
            review_packet=opb._require_blinded_review_packet(blinded, expected_item_count=9),  # noqa: SLF001
            known_hashes=known_hashes,
        )

    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping"):
        opb._load_yaml_mapping(list_yaml)  # noqa: SLF001

    with pytest.raises(ValueError, match="keys must be strings"):
        opb._required_string_keyed_mapping({1: "x"}, "field")  # noqa: SLF001
    with pytest.raises(ValueError, match="field is required"):
        opb._required_string_keyed_mapping([], "field")  # noqa: SLF001
    with pytest.raises(ValueError, match="field is required"):
        opb._required_string_list("x", "field")  # noqa: SLF001
    with pytest.raises(ValueError, match="values must be strings"):
        opb._required_string_list(["x", 1], "field")  # noqa: SLF001
    with pytest.raises(ValueError, match="field is required"):
        opb._required_string_list([], "field")  # noqa: SLF001
    with pytest.raises(ValueError, match="field is required"):
        opb._required_string({}, "field")  # noqa: SLF001
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        opb._required_sha256({"field": "abc"}, "field")  # noqa: SLF001


def test_packet_validation_does_not_require_historical_scratch_paths() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()
    relocated = copy.deepcopy(baseline)
    relocated["scratch_runtime"]["db_path"] = "/tmp/nsqd-jepa-baselines-relocated/nsqd.sqlite"
    relocated["scratch_runtime"]["index_path"] = "/tmp/nsqd-jepa-baselines-relocated/index"

    summary = evaluate_matched_count_operator_baselines(
        results["proposed_ideas"],
        extracted_facts=results["extracted_facts"],
        baseline_execution=relocated,
        operator_e_candidates=e_candidates["candidates"],
        blinded_review_packet=blinded,
        audit_manifest=audit,
    )

    assert summary["matched_candidate_count"] == 3
    assert summary["operator_a_baseline_status"] == "executed_report_only"
    assert summary["operator_b_baseline_status"] == "executed_report_only"


def test_blinded_packet_content_must_bind_artifact_content_even_after_digest_reseal() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()
    tampered = copy.deepcopy(blinded)
    tampered["items"][0]["proposal_summary"] += " Extra ungrounded claim."
    tampered["packet_digest"] = opb.blinded_review_packet_digest(tampered)  # noqa: SLF001
    resealed_audit = copy.deepcopy(audit)
    resealed_audit["review_packet_digest"] = tampered["packet_digest"]
    resealed_audit["manifest_digest"] = opb.audit_manifest_digest(resealed_audit)  # noqa: SLF001
    with pytest.raises(ValueError, match="blinded review item content"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=tampered,
            audit_manifest=resealed_audit,
        )


def test_operator_baselines_validate_declared_projection_hashes_and_operator_e_atypicality() -> (
    None
):
    results, baseline, e_candidates, blinded, audit = _payloads()

    wrong_declared_projection = copy.deepcopy(baseline)
    wrong_declared_projection["projection_bindings"][0]["manifest_declared_projection_sha256"] = (
        "0" * 64
    )
    with pytest.raises(ValueError, match="manifest_declared_projection_sha256"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=wrong_declared_projection,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    wrong_declared_excerpt = copy.deepcopy(baseline)
    wrong_declared_excerpt["projection_bindings"][0]["manifest_declared_excerpt_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest_declared_excerpt_sha256"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=wrong_declared_excerpt,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    wrong_binding_policy = copy.deepcopy(baseline)
    wrong_binding_policy["projection_bindings"][0]["domain_policy_id"] = "optimization/1"
    with pytest.raises(ValueError, match="binding domain_policy_id"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=wrong_binding_policy,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )

    wrong_atypicality = copy.deepcopy(e_candidates)
    wrong_atypicality["candidates"][0]["atypicality"]["interpretation"] = "novelty"
    with pytest.raises(ValueError, match="atypicality_interpretation"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=wrong_atypicality["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_projection_bindings_reject_symlinked_manifest_projection_excerpt_and_aliases(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    projection = real_root / "rec.yaml"
    projection.write_text(
        "\n".join(
            [
                "source_paper_id: doi:10.1/x",
                "source: doi:10.1/x",
                "domain_policy_id: finance/1",
                "paraphrase: candidate text",
                "paraphrase_source: model_assisted",
                "source_abstract_sha256: " + ("a" * 64),
                "source_markdown_sha256: " + ("b" * 64),
                "paraphrase_sha256: " + ("c" * 64),
                "human_reviewer: product",
                "human_approved_at: 2026-01-01T00:00:00+00:00",
                "review_status: approved",
                "title: X",
                "",
            ]
        ),
        encoding="utf-8",
    )
    excerpt = real_root / "rec.md"
    excerpt.write_text("excerpt\n", encoding="utf-8")
    payload = opb._load_yaml_mapping(projection)  # noqa: SLF001
    projection_sha = opb.sha256_hex(projection.read_bytes())
    excerpt_sha = opb.sha256_hex(excerpt.read_bytes())
    reviewed_sha = canonical_reviewed_projection_digest(payload)
    manifest_target = real_root / "manifest-target.toml"
    lines = ["schema_version = 1", ""]
    for rid in opb.APPROVED_FINANCE_RECORD_IDS:
        lines.extend(
            [
                f"[fixture.{rid}]",
                f'id = "{rid}"',
                'path = "rec.yaml"',
                'excerpt_path = "rec.md"',
                'domain_policy_id = "finance/1"',
                f'content_sha256 = "{projection_sha}"',
                f'excerpt_sha256 = "{excerpt_sha}"',
                f'reviewed_projection_sha256 = "{reviewed_sha}"',
                "",
            ]
        )
    manifest_target.write_text("\n".join(lines), encoding="utf-8")

    def rows(
        *, base: str, manifest_name: str, projection_name: str, excerpt_name: str
    ) -> list[dict[str, str]]:
        return [
            {
                "approved_record_id": rid,
                "projected_record_id": opb.projection_record_id(payload),  # noqa: SLF001
                "domain_policy_id": "finance/1",
                "source_paper_id": "doi:10.1/x",
                "title": "X",
                "manifest_path": f"{base}/{manifest_name}",
                "projection_path": f"{base}/{projection_name}",
                "projection_sha256": projection_sha,
                "manifest_declared_projection_sha256": projection_sha,
                "approved_excerpt": f"{base}/{excerpt_name}",
                "approved_excerpt_sha256": excerpt_sha,
                "manifest_declared_excerpt_sha256": excerpt_sha,
                "reviewed_projection_digest": reviewed_sha,
            }
            for rid in opb.APPROVED_FINANCE_RECORD_IDS
        ]

    original_root = opb.REPO_ROOT
    original_fixture_manifest = opb.APPROVED_FIXTURE_MANIFEST_PATH
    original_final_manifest = opb.APPROVED_FINAL_MANIFEST_PATH
    original_fixture_root = opb.APPROVED_FIXTURE_ROOT
    original_final_root = opb.APPROVED_FINAL_ROOT
    opb.REPO_ROOT = tmp_path
    try:
        manifest_link_dir = tmp_path / "approved-manifest"
        manifest_link_dir.mkdir()
        (manifest_link_dir / "manifest.toml").symlink_to(manifest_target)
        (manifest_link_dir / "rec.yaml").write_bytes(projection.read_bytes())
        (manifest_link_dir / "rec.md").write_bytes(excerpt.read_bytes())
        opb.APPROVED_FIXTURE_MANIFEST_PATH = Path("approved-manifest/manifest.toml")
        opb.APPROVED_FINAL_MANIFEST_PATH = Path("approved-manifest/manifest.toml")
        opb.APPROVED_FIXTURE_ROOT = Path("approved-manifest")
        opb.APPROVED_FINAL_ROOT = Path("approved-manifest")
        with pytest.raises(ValueError, match="symlink"):
            opb._require_projection_bindings(  # noqa: SLF001
                rows(
                    base="approved-manifest",
                    manifest_name="manifest.toml",
                    projection_name="rec.yaml",
                    excerpt_name="rec.md",
                )
            )

        projection_link_dir = tmp_path / "approved-projection"
        projection_link_dir.mkdir()
        (projection_link_dir / "manifest.toml").write_text(
            manifest_target.read_text(), encoding="utf-8"
        )
        (projection_link_dir / "rec.yaml").symlink_to(projection)
        (projection_link_dir / "rec.md").write_bytes(excerpt.read_bytes())
        opb.APPROVED_FIXTURE_MANIFEST_PATH = Path("approved-projection/manifest.toml")
        opb.APPROVED_FINAL_MANIFEST_PATH = Path("approved-projection/manifest.toml")
        opb.APPROVED_FIXTURE_ROOT = Path("approved-projection")
        opb.APPROVED_FINAL_ROOT = Path("approved-projection")
        with pytest.raises(ValueError, match="symlink"):
            opb._require_projection_bindings(  # noqa: SLF001
                rows(
                    base="approved-projection",
                    manifest_name="manifest.toml",
                    projection_name="rec.yaml",
                    excerpt_name="rec.md",
                )
            )

        excerpt_link_dir = tmp_path / "approved-excerpt"
        excerpt_link_dir.mkdir()
        (excerpt_link_dir / "manifest.toml").write_text(
            manifest_target.read_text(), encoding="utf-8"
        )
        (excerpt_link_dir / "rec.yaml").write_bytes(projection.read_bytes())
        (excerpt_link_dir / "rec.md").symlink_to(excerpt)
        opb.APPROVED_FIXTURE_MANIFEST_PATH = Path("approved-excerpt/manifest.toml")
        opb.APPROVED_FINAL_MANIFEST_PATH = Path("approved-excerpt/manifest.toml")
        opb.APPROVED_FIXTURE_ROOT = Path("approved-excerpt")
        opb.APPROVED_FINAL_ROOT = Path("approved-excerpt")
        with pytest.raises(ValueError, match="symlink"):
            opb._require_projection_bindings(  # noqa: SLF001
                rows(
                    base="approved-excerpt",
                    manifest_name="manifest.toml",
                    projection_name="rec.yaml",
                    excerpt_name="rec.md",
                )
            )

        alias_parent = tmp_path / "approved-alias"
        alias_parent.mkdir()
        nested_real = alias_parent / "real-nested"
        nested_real.mkdir()
        (nested_real / "manifest.toml").write_text(manifest_target.read_text(), encoding="utf-8")
        (nested_real / "rec.yaml").write_bytes(projection.read_bytes())
        (nested_real / "rec.md").write_bytes(excerpt.read_bytes())
        (alias_parent / "nested").symlink_to(nested_real, target_is_directory=True)
        opb.APPROVED_FIXTURE_MANIFEST_PATH = Path("approved-alias/nested/manifest.toml")
        opb.APPROVED_FINAL_MANIFEST_PATH = Path("approved-alias/nested/manifest.toml")
        opb.APPROVED_FIXTURE_ROOT = Path("approved-alias/nested")
        opb.APPROVED_FINAL_ROOT = Path("approved-alias/nested")
        with pytest.raises(ValueError, match="symlink"):
            opb._require_projection_bindings(  # noqa: SLF001
                rows(
                    base="approved-alias/nested",
                    manifest_name="manifest.toml",
                    projection_name="rec.yaml",
                    excerpt_name="rec.md",
                )
            )
    finally:
        opb.REPO_ROOT = original_root
        opb.APPROVED_FIXTURE_MANIFEST_PATH = original_fixture_manifest
        opb.APPROVED_FINAL_MANIFEST_PATH = original_final_manifest
        opb.APPROVED_FIXTURE_ROOT = original_fixture_root
        opb.APPROVED_FINAL_ROOT = original_final_root


def test_receipt_verifier_rejects_unconfined_or_unprefixed_runtime_paths(tmp_path: Path) -> None:
    import sqlite3

    scratch = tmp_path / "plain-scratch"
    scratch.mkdir()
    db_path = scratch / "nsqd.sqlite"
    index_path = scratch / "index"
    index_path.mkdir()
    (index_path / "part-1.bin").write_bytes(b"index-bytes")
    candidate_payload = {"candidate": {"title": "x"}, "operator": "A"}
    card_payload = {"card_id": "h1", "title": "x"}
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE nsqd_candidates "
            "(artifact_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE nsqd_frontier_cards "
            "(card_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
            ["h1", json.dumps(candidate_payload)],
        )
        conn.execute(
            "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) VALUES (?, ?, ?)",
            ["h1", "cell-1", json.dumps(card_payload)],
        )
        conn.commit()
    finally:
        conn.close()
    receipt = {
        "sqlite_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "lancedb_tree_sha256": opb.lancedb_tree_digest(index_path),
        "candidate_count": 1,
        "card_count": 1,
        "candidate_artifact_hashes": ["h1"],
        "frontier_card_hashes": ["h1"],
        "candidate_payload_sha256": {"h1": opb._canonical_payload_sha256(candidate_payload)},  # noqa: SLF001
        "frontier_card_payload_sha256": {"h1": opb._canonical_payload_sha256(card_payload)},  # noqa: SLF001
    }
    with pytest.raises(ValueError, match="dedicated nsqd-jepa-baselines"):
        verify_scratch_execution_receipt(
            receipt,
            scratch_runtime={
                "db_path": str(db_path),
                "index_path": str(index_path),
                "no_production_writes": True,
                "production_write_paths": [],
            },
        )


def test_replay_script_requires_a_fresh_nonexistent_scratch_dir() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    existing = Path("/tmp/nsqd-jepa-baselines-existing")
    existing.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="fresh non-existent"):
        replay._build_container(existing, embedder=object())


def test_optional_scratch_receipt_verifier_checks_local_sqlite_and_index(tmp_path: Path) -> None:
    import hashlib
    import json
    import sqlite3

    scratch = tmp_path / "nsqd-jepa-baselines-local"
    scratch.mkdir()
    db_path = scratch / "nsqd.sqlite"
    index_path = scratch / "index"
    index_path.mkdir()
    (index_path / "part-1.bin").write_bytes(b"index-bytes")

    candidate_payload = {"candidate": {"title": "x"}, "operator": "A"}
    card_payload = {"card_id": "h1", "title": "x"}
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE nsqd_candidates "
            "(artifact_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE nsqd_frontier_cards "
            "(card_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
            ["h1", json.dumps(candidate_payload)],
        )
        conn.execute(
            "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) VALUES (?, ?, ?)",
            ["h1", "cell-1", json.dumps(card_payload)],
        )
        conn.commit()
    finally:
        conn.close()

    receipt = {
        "sqlite_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "lancedb_tree_sha256": opb.lancedb_tree_digest(index_path),
        "candidate_count": 1,
        "card_count": 1,
        "candidate_artifact_hashes": ["h1"],
        "frontier_card_hashes": ["h1"],
        "candidate_payload_sha256": {"h1": opb._canonical_payload_sha256(candidate_payload)},
        "frontier_card_payload_sha256": {"h1": opb._canonical_payload_sha256(card_payload)},
    }
    runtime = verify_scratch_execution_receipt(
        receipt,
        scratch_runtime={
            "db_path": str(db_path),
            "index_path": str(index_path),
            "no_production_writes": True,
            "production_write_paths": [],
        },
    )
    assert sorted(runtime["candidate_payloads"]) == ["h1"]
    assert sorted(runtime["frontier_card_payloads"]) == ["h1"]

    broken = {**receipt, "sqlite_sha256": "0" * 64}
    with pytest.raises(ValueError, match="sqlite_sha256"):
        verify_scratch_execution_receipt(
            broken,
            scratch_runtime={
                "db_path": str(db_path),
                "index_path": str(index_path),
                "no_production_writes": True,
                "production_write_paths": [],
            },
        )


def test_projection_bindings_read_actual_manifest_row_hashes(tmp_path: Path) -> None:
    projection_dir = tmp_path / "approved"
    projection_dir.mkdir()
    projection = projection_dir / "rec.yaml"
    projection.write_text(
        "\n".join(
            [
                "source_paper_id: doi:10.1/x",
                "source: doi:10.1/x",
                "domain_policy_id: finance/1",
                "paraphrase: candidate text",
                "paraphrase_source: model_assisted",
                "source_abstract_sha256: " + ("a" * 64),
                "source_markdown_sha256: " + ("b" * 64),
                "paraphrase_sha256: " + ("c" * 64),
                "human_reviewer: product",
                "human_approved_at: 2026-01-01T00:00:00+00:00",
                "review_status: approved",
                "title: X",
                "",
            ]
        ),
        encoding="utf-8",
    )
    excerpt = projection_dir / "rec.md"
    excerpt.write_text("excerpt\n", encoding="utf-8")
    payload = opb._load_yaml_mapping(projection)  # noqa: SLF001
    projection_sha = opb.sha256_hex(projection.read_bytes())
    excerpt_sha = opb.sha256_hex(excerpt.read_bytes())
    reviewed_sha = canonical_reviewed_projection_digest(payload)
    manifest = projection_dir / "manifest.toml"

    def write_manifest(*, content_sha: str, excerpt_sha_value: str) -> None:
        lines = ["schema_version = 1", ""]
        for rid in opb.APPROVED_FINANCE_RECORD_IDS:
            lines.extend(
                [
                    f"[fixture.{rid}]",
                    f'id = "{rid}"',
                    'path = "rec.yaml"',
                    'excerpt_path = "rec.md"',
                    'domain_policy_id = "finance/1"',
                    f'content_sha256 = "{content_sha}"',
                    f'excerpt_sha256 = "{excerpt_sha_value}"',
                    f'reviewed_projection_sha256 = "{reviewed_sha}"',
                    "",
                ]
            )
        manifest.write_text("\n".join(lines), encoding="utf-8")

    def rows() -> list[dict[str, str]]:
        return [
            {
                "approved_record_id": rid,
                "projected_record_id": opb.projection_record_id(payload),  # noqa: SLF001
                "domain_policy_id": "finance/1",
                "source_paper_id": "doi:10.1/x",
                "title": "X",
                "manifest_path": "approved/manifest.toml",
                "projection_path": "approved/rec.yaml",
                "projection_sha256": projection_sha,
                "manifest_declared_projection_sha256": projection_sha,
                "approved_excerpt": "approved/rec.md",
                "approved_excerpt_sha256": excerpt_sha,
                "manifest_declared_excerpt_sha256": excerpt_sha,
                "reviewed_projection_digest": reviewed_sha,
            }
            for rid in opb.APPROVED_FINANCE_RECORD_IDS
        ]

    original_root = opb.REPO_ROOT
    original_fixture_manifest = opb.APPROVED_FIXTURE_MANIFEST_PATH
    original_final_manifest = opb.APPROVED_FINAL_MANIFEST_PATH
    original_fixture_root = opb.APPROVED_FIXTURE_ROOT
    original_final_root = opb.APPROVED_FINAL_ROOT
    opb.REPO_ROOT = tmp_path
    opb.APPROVED_FIXTURE_MANIFEST_PATH = Path("approved/manifest.toml")
    opb.APPROVED_FINAL_MANIFEST_PATH = Path("approved/manifest.toml")
    opb.APPROVED_FIXTURE_ROOT = Path("approved")
    opb.APPROVED_FINAL_ROOT = Path("approved")
    try:
        write_manifest(content_sha="0" * 64, excerpt_sha_value=excerpt_sha)
        with pytest.raises(ValueError, match="manifest row content_sha256"):
            opb._require_projection_bindings(rows())  # noqa: SLF001
        write_manifest(content_sha=projection_sha, excerpt_sha_value="0" * 64)
        with pytest.raises(ValueError, match="manifest row excerpt_sha256"):
            opb._require_projection_bindings(rows())  # noqa: SLF001
    finally:
        opb.REPO_ROOT = original_root
        opb.APPROVED_FIXTURE_MANIFEST_PATH = original_fixture_manifest
        opb.APPROVED_FINAL_MANIFEST_PATH = original_final_manifest
        opb.APPROVED_FIXTURE_ROOT = original_fixture_root
        opb.APPROVED_FINAL_ROOT = original_final_root


def test_replay_script_compares_logical_replay_fields_but_not_physical_receipt_bytes() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    baseline = _json("baseline-evidence.json")
    generated_a = [
        {
            "candidate_id": row["candidate_id"],
            "candidate_artifact_hash": row["candidate_artifact_hash"],
            "candidate_artifact": copy.deepcopy(row["candidate_artifact"]),
            "grounding": copy.deepcopy(row["grounding"]),
            "scored_card": copy.deepcopy(row["scored_card"]),
        }
        for row in baseline["operator_a_artifacts"]
    ]
    generated_b = [
        {
            "candidate_id": row["candidate_id"],
            "candidate_artifact_hash": row["candidate_artifact_hash"],
            "candidate_artifact": copy.deepcopy(row["candidate_artifact"]),
            "grounding": copy.deepcopy(row["grounding"]),
            "scored_card": copy.deepcopy(row["scored_card"]),
        }
        for row in baseline["operator_b_artifacts"]
    ]

    logical_receipt = copy.deepcopy(baseline["execution_receipt"])
    logical_receipt["sqlite_sha256"] = "0" * 64
    logical_receipt["lancedb_tree_sha256"] = "f" * 64
    replay._compare_generated_to_packet(baseline, generated_a, generated_b, logical_receipt)

    tolerated = copy.deepcopy(generated_a)
    tolerated[1]["candidate_artifact"]["grounding"]["evidence"] = 0.4457170383450661
    tolerated[1]["grounding"]["evidence"] = 0.4457170383450661
    tolerated[1]["candidate_artifact"]["grounding"]["neighbors"][2]["distance"] = 0.4751366701368107
    tolerated[1]["grounding"]["neighbors"][2]["distance"] = 0.4751366701368107
    tolerated[1]["candidate_artifact"]["grounding"]["measurement_artifact_digest"] = (
        tau_measurement_artifact_digest(tolerated[1]["candidate_artifact"]["grounding"])
    )
    tolerated[1]["grounding"]["measurement_artifact_digest"] = tau_measurement_artifact_digest(
        tolerated[1]["grounding"]
    )
    tolerated[2]["candidate_artifact"]["grounding"]["evidence"] = 0.46667141193784384
    tolerated[2]["grounding"]["evidence"] = 0.46667141193784384
    tolerated[2]["candidate_artifact"]["grounding"]["measurement_artifact_digest"] = (
        tau_measurement_artifact_digest(tolerated[2]["candidate_artifact"]["grounding"])
    )
    tolerated[2]["grounding"]["measurement_artifact_digest"] = tau_measurement_artifact_digest(
        tolerated[2]["grounding"]
    )
    replay._compare_generated_to_packet(baseline, tolerated, generated_b, logical_receipt)

    drifted_grounding = copy.deepcopy(generated_a)
    drifted_grounding[0]["grounding"]["measurement"]["distances"][0] = 0.99
    with pytest.raises(ValueError, match=r"A-BASE-01.*grounding.*measurement\.distances\[0\]"):
        replay._compare_generated_to_packet(
            baseline,
            drifted_grounding,
            generated_b,
            logical_receipt,
        )

    payload_sha_drift = copy.deepcopy(logical_receipt)
    first_hash = payload_sha_drift["candidate_artifact_hashes"][0]
    payload_sha_drift["candidate_payload_sha256"][first_hash] = "a" * 64
    payload_sha_drift["frontier_card_payload_sha256"][first_hash] = "b" * 64
    replay._compare_generated_to_packet(baseline, tolerated, generated_b, payload_sha_drift)

    nan_drift = copy.deepcopy(generated_a)
    nan_drift[0]["grounding"]["evidence"] = float("nan")
    with pytest.raises(ValueError, match=r"A-BASE-01.*grounding.*grounding\.evidence"):
        replay._compare_generated_to_packet(baseline, nan_drift, generated_b, logical_receipt)

    inf_drift = copy.deepcopy(generated_a)
    inf_drift[0]["grounding"]["evidence"] = float("inf")
    with pytest.raises(ValueError, match=r"A-BASE-01.*grounding.*grounding\.evidence"):
        replay._compare_generated_to_packet(baseline, inf_drift, generated_b, logical_receipt)

    type_drift = copy.deepcopy(generated_a)
    type_drift[0]["grounding"]["measurement"]["distances"][0] = "0.1"
    with pytest.raises(ValueError, match=r"A-BASE-01.*grounding.*measurement\.distances\[0\]"):
        replay._compare_generated_to_packet(baseline, type_drift, generated_b, logical_receipt)

    structural_drift = copy.deepcopy(generated_a)
    structural_drift[0]["candidate_artifact"]["candidate"].pop("title")
    with pytest.raises(ValueError, match=r"A-BASE-01.*candidate_artifact.*candidate\.keys"):
        replay._compare_generated_to_packet(
            baseline,
            structural_drift,
            generated_b,
            logical_receipt,
        )


def test_replay_logical_comparator_exactly_compares_non_measurement_digest_keys() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    generated = {
        "measurement_artifact_digest": "0" * 64,
        "payload": {"value": 1},
    }
    packet_value = {
        "measurement_artifact_digest": "f" * 64,
        "payload": {"value": 1},
    }
    with pytest.raises(
        ValueError, match=r"A-BASE-03.*payload.*payload\.measurement_artifact_digest"
    ):
        replay._assert_fresh_logical_match(
            candidate_id="A-BASE-03",
            field="payload",
            generated=generated,
            packet_value=packet_value,
        )


def test_replay_logical_comparator_validates_per_side_measurement_artifact_digest() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    baseline = _json("baseline-evidence.json")
    generated_a = [
        {
            "candidate_id": row["candidate_id"],
            "candidate_artifact_hash": row["candidate_artifact_hash"],
            "candidate_artifact": copy.deepcopy(row["candidate_artifact"]),
            "grounding": copy.deepcopy(row["grounding"]),
            "scored_card": copy.deepcopy(row["scored_card"]),
        }
        for row in baseline["operator_a_artifacts"]
    ]
    generated_b = [
        {
            "candidate_id": row["candidate_id"],
            "candidate_artifact_hash": row["candidate_artifact_hash"],
            "candidate_artifact": copy.deepcopy(row["candidate_artifact"]),
            "grounding": copy.deepcopy(row["grounding"]),
            "scored_card": copy.deepcopy(row["scored_card"]),
        }
        for row in baseline["operator_b_artifacts"]
    ]
    logical_receipt = copy.deepcopy(baseline["execution_receipt"])
    logical_receipt["sqlite_sha256"] = "0" * 64
    logical_receipt["lancedb_tree_sha256"] = "f" * 64

    drifted = copy.deepcopy(generated_a)
    drifted[2]["candidate_artifact"]["grounding"]["evidence"] = 0.46667141193784384
    drifted[2]["grounding"]["evidence"] = 0.46667141193784384
    drifted[2]["candidate_artifact"]["grounding"]["measurement_artifact_digest"] = (
        tau_measurement_artifact_digest(drifted[2]["candidate_artifact"]["grounding"])
    )
    drifted[2]["grounding"]["measurement_artifact_digest"] = tau_measurement_artifact_digest(
        drifted[2]["grounding"]
    )
    replay._compare_generated_to_packet(baseline, drifted, generated_b, logical_receipt)

    tampered_generated_digest = copy.deepcopy(drifted)
    tampered_generated_digest[2]["grounding"]["measurement_artifact_digest"] = "0" * 64
    with pytest.raises(
        ValueError,
        match=r"A-BASE-03.*grounding.*measurement_artifact_digest",
    ):
        replay._compare_generated_to_packet(
            baseline,
            tampered_generated_digest,
            generated_b,
            logical_receipt,
        )

    tampered_packet_digest = copy.deepcopy(baseline)
    tampered_packet_digest["operator_a_artifacts"][2]["grounding"][
        "measurement_artifact_digest"
    ] = "0" * 64
    with pytest.raises(
        ValueError,
        match=r"A-BASE-03.*grounding.*measurement_artifact_digest",
    ):
        replay._compare_generated_to_packet(
            tampered_packet_digest,
            drifted,
            generated_b,
            logical_receipt,
        )

    non_float_measurement_drift = copy.deepcopy(drifted)
    non_float_measurement_drift[2]["grounding"]["measurement"]["k"] = 4
    non_float_measurement_drift[2]["grounding"]["measurement_artifact_digest"] = (
        tau_measurement_artifact_digest(non_float_measurement_drift[2]["grounding"])
    )
    with pytest.raises(
        ValueError,
        match=r"A-BASE-03.*grounding.*measurement\.k",
    ):
        replay._compare_generated_to_packet(
            baseline,
            non_float_measurement_drift,
            generated_b,
            logical_receipt,
        )

    digest_only_drift = copy.deepcopy(generated_a)
    digest_only_drift[2]["grounding"]["measurement_artifact_digest"] = (
        tau_measurement_artifact_digest(digest_only_drift[2]["grounding"])
    )[:-1] + "0"
    with pytest.raises(
        ValueError,
        match=r"A-BASE-03.*grounding.*measurement_artifact_digest",
    ):
        replay._compare_generated_to_packet(
            baseline,
            digest_only_drift,
            generated_b,
            logical_receipt,
        )


def test_replay_logical_comparator_rejects_out_of_bound_float_and_list_order() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    assert replay.FRESH_LOGICAL_FLOAT_TOLERANCE == 1e-3
    with pytest.raises(ValueError, match=r"A-BASE-02.*field.*field\.value"):
        replay._assert_fresh_logical_match(
            candidate_id="A-BASE-02",
            field="field",
            generated={"value": 0.5},
            packet_value={"value": 0.5015},
        )
    with pytest.raises(ValueError, match=r"A-BASE-02.*field.*field\[0\]"):
        replay._assert_fresh_logical_match(
            candidate_id="A-BASE-02",
            field="field",
            generated=["a", "b"],
            packet_value=["b", "a"],
        )


def test_private_hardened_helper_paths_and_bounded_tree_hashing(
    tmp_path: Path, monkeypatch
) -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()

    swapped_blind_ids = copy.deepcopy(audit)
    (
        swapped_blind_ids["items"][0]["blind_id"],
        swapped_blind_ids["items"][1]["blind_id"],
    ) = (
        swapped_blind_ids["items"][1]["blind_id"],
        swapped_blind_ids["items"][0]["blind_id"],
    )
    swapped_blind_ids["manifest_digest"] = opb.audit_manifest_digest(swapped_blind_ids)  # noqa: SLF001
    with pytest.raises(ValueError, match="blind_id order"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=e_candidates["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=swapped_blind_ids,
        )

    with pytest.raises(ValueError, match="db_path must target nsqd.sqlite"):
        opb._require_confined_scratch_runtime_paths(  # noqa: SLF001
            db_path=tmp_path / "nsqd-jepa-baselines-bad" / "wrong.sqlite",
            index_path=tmp_path / "nsqd-jepa-baselines-bad" / "index",
        )
    with pytest.raises(ValueError, match="index_path must target the index directory"):
        opb._require_confined_scratch_runtime_paths(  # noqa: SLF001
            db_path=tmp_path / "nsqd-jepa-baselines-bad" / "nsqd.sqlite",
            index_path=tmp_path / "nsqd-jepa-baselines-bad" / "wrong-index",
        )
    with pytest.raises(ValueError, match="share one scratch directory"):
        opb._require_confined_scratch_runtime_paths(  # noqa: SLF001
            db_path=tmp_path / "nsqd-jepa-baselines-a" / "nsqd.sqlite",
            index_path=tmp_path / "nsqd-jepa-baselines-b" / "index",
        )
    with pytest.raises(ValueError, match="allowlisted system temp root"):
        opb._require_confined_scratch_runtime_paths(  # noqa: SLF001
            db_path=REPO_ROOT / "nsqd-jepa-baselines-bad" / "nsqd.sqlite",
            index_path=REPO_ROOT / "nsqd-jepa-baselines-bad" / "index",
        )
    assert (
        opb._matching_allowed_temp_root(  # noqa: SLF001
            Path("/tmp/nsqd-jepa-baselines-ok"),
            Path("/private/tmp/nsqd-jepa-baselines-ok"),
        )
        is not None
    )
    assert opb._matching_allowed_temp_root(REPO_ROOT, REPO_ROOT.resolve()) is None  # noqa: SLF001

    original_root = opb.REPO_ROOT
    opb.REPO_ROOT = tmp_path
    try:
        approved = tmp_path / "approved"
        approved.mkdir()
        regular = approved / "good.txt"
        regular.write_text("ok", encoding="utf-8")
        assert (
            opb._read_verified_repo_file(  # noqa: SLF001
                relative_path=Path("approved/good.txt"),
                expected_root=Path("approved"),
                field="projection_path",
            )
            == b"ok"
        )
        with pytest.raises(ValueError, match="outside the approved root"):
            opb._read_verified_repo_file(  # noqa: SLF001
                relative_path=Path("other/good.txt"),
                expected_root=Path("approved"),
                field="projection_path",
            )
        with pytest.raises(ValueError, match="is missing"):
            opb._read_verified_repo_file(  # noqa: SLF001
                relative_path=Path("approved/missing.txt"),
                expected_root=Path("approved"),
                field="projection_path",
            )
        directory = approved / "dir"
        directory.mkdir()
        with pytest.raises(ValueError, match="regular file"):
            opb._read_verified_repo_file(  # noqa: SLF001
                relative_path=Path("approved/dir"),
                expected_root=Path("approved"),
                field="projection_path",
            )
    finally:
        opb.REPO_ROOT = original_root

    tree = tmp_path / "tree-bounds"
    tree.mkdir()
    (tree / "a.bin").write_bytes(b"a")
    link_target = tmp_path / "target.bin"
    link_target.write_bytes(b"b")
    (tree / "link.bin").symlink_to(link_target)
    with pytest.raises(ValueError, match="must not contain symlinks"):
        opb.lancedb_tree_digest(tree)
    (tree / "link.bin").unlink()
    monkeypatch.setattr(opb, "MAX_RECEIPT_TREE_FILES", 1)
    (tree / "b.bin").write_bytes(b"b")
    with pytest.raises(ValueError, match="file limit"):
        opb.lancedb_tree_digest(tree)
    monkeypatch.setattr(opb, "MAX_RECEIPT_TREE_FILES", 4096)
    monkeypatch.setattr(opb, "MAX_RECEIPT_TREE_BYTES", 1)
    with pytest.raises(ValueError, match="byte limit"):
        opb.lancedb_tree_digest(tree)


def test_replay_script_requires_direct_existing_temp_root_child_and_public_helpers(
    tmp_path: Path, monkeypatch
) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    assert hasattr(replay, "read_verified_repo_file")
    assert hasattr(replay, "load_verified_yaml_mapping")

    nested_parent = tmp_path / "missing-parent" / "nested"
    candidate = nested_parent / "nsqd-jepa-baselines-race"
    with pytest.raises(ValueError, match="direct child|existing temp root|fresh non-existent"):
        replay._build_container(candidate, embedder=object())

    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(Path("/tmp"), target_is_directory=True)
    with pytest.raises(ValueError, match="symlink alias|direct child"):
        replay._guard_scratch_dir(alias_parent / "nsqd-jepa-baselines-race")


def test_execution_receipt_sqlite_hashing_streams_and_enforces_size_bounds(
    tmp_path: Path, monkeypatch
) -> None:
    import sqlite3

    scratch = tmp_path / "nsqd-jepa-baselines-stream"
    scratch.mkdir()
    db_path = scratch / "nsqd.sqlite"
    index_path = scratch / "index"
    index_path.mkdir()
    (index_path / "part-1.bin").write_bytes(b"index-bytes")
    candidate_payload = {"candidate": {"title": "x"}, "operator": "A"}
    card_payload = {"card_id": "h1", "title": "x"}
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE nsqd_candidates "
            "(artifact_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE nsqd_frontier_cards "
            "(card_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
            ["h1", json.dumps(candidate_payload)],
        )
        conn.execute(
            "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) VALUES (?, ?, ?)",
            ["h1", "cell-1", json.dumps(card_payload)],
        )
        conn.commit()
    finally:
        conn.close()

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(self: Path) -> bytes:
        if self == db_path:
            raise AssertionError("sqlite hash must stream, not read_bytes")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    sqlite_sha = opb.sha256_file_digest(db_path)  # noqa: SLF001
    receipt = {
        "sqlite_sha256": sqlite_sha,
        "lancedb_tree_sha256": opb.lancedb_tree_digest(index_path),
        "candidate_count": 1,
        "card_count": 1,
        "candidate_artifact_hashes": ["h1"],
        "frontier_card_hashes": ["h1"],
        "candidate_payload_sha256": {"h1": opb._canonical_payload_sha256(candidate_payload)},  # noqa: SLF001
        "frontier_card_payload_sha256": {"h1": opb._canonical_payload_sha256(card_payload)},  # noqa: SLF001
    }
    runtime = verify_scratch_execution_receipt(
        receipt,
        scratch_runtime={
            "db_path": str(db_path),
            "index_path": str(index_path),
            "no_production_writes": True,
            "production_write_paths": [],
        },
    )
    assert sorted(runtime["candidate_payloads"]) == ["h1"]

    monkeypatch.setattr(opb, "MAX_RECEIPT_SQLITE_BYTES", 1)
    with pytest.raises(ValueError, match="sqlite exceeds the verified byte limit"):
        opb.sha256_file_digest(db_path)  # noqa: SLF001


def test_operator_e_candidates_require_nearest_prior_combinations_field() -> None:
    results, baseline, e_candidates, blinded, audit = _payloads()
    missing_field = copy.deepcopy(e_candidates)
    missing_field["candidates"][0].pop("nearest_prior_combinations", None)
    with pytest.raises(ValueError, match="nearest_prior_combinations"):
        evaluate_matched_count_operator_baselines(
            results["proposed_ideas"],
            extracted_facts=results["extracted_facts"],
            baseline_execution=baseline,
            operator_e_candidates=missing_field["candidates"],
            blinded_review_packet=blinded,
            audit_manifest=audit,
        )


def test_public_trusted_file_helpers_stream_and_validate_yaml(tmp_path: Path) -> None:
    repo_root = tmp_path
    approved = repo_root / "approved"
    approved.mkdir()
    yaml_path = approved / "row.yaml"
    yaml_path.write_text("title: ok\nsource_paper_id: doi:x\n", encoding="utf-8")
    loaded = trusted_files.load_verified_yaml_mapping(
        repo_root=repo_root,
        relative_path=Path("approved/row.yaml"),
        expected_root=Path("approved"),
        field="projection_path",
    )
    assert loaded["title"] == "ok"

    bad_yaml = approved / "bad.yaml"
    bad_yaml.write_text("- bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping"):
        trusted_files.load_verified_yaml_mapping(
            repo_root=repo_root,
            relative_path=Path("approved/bad.yaml"),
            expected_root=Path("approved"),
            field="projection_path",
        )

    with pytest.raises(ValueError, match="max_bytes must be positive"):
        trusted_files.sha256_file_digest(yaml_path, max_bytes=0)

    symlink_root = repo_root / "symlink-root"
    symlink_root.symlink_to(approved, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        trusted_files.read_verified_repo_file(
            repo_root=repo_root,
            relative_path=Path("symlink-root/row.yaml"),
            expected_root=Path("symlink-root"),
            field="projection_path",
        )


def test_public_trusted_file_helpers_bound_repo_reads(tmp_path: Path) -> None:
    repo_root = tmp_path
    approved = repo_root / "approved"
    approved.mkdir()
    yaml_path = approved / "row.yaml"
    yaml_path.write_text("title: ok\nsource_paper_id: doi:x\n", encoding="utf-8")

    assert (
        trusted_files.read_verified_repo_file(
            repo_root=repo_root,
            relative_path=Path("approved/row.yaml"),
            expected_root=Path("approved"),
            field="projection_path",
            max_bytes=64,
        )
        == yaml_path.read_bytes()
    )

    outside = repo_root / "outside.yaml"
    outside.write_text("title: secret\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside the approved root"):
        trusted_files.read_verified_repo_file(
            repo_root=repo_root,
            relative_path=Path("approved/../outside.yaml"),
            expected_root=Path("approved"),
            field="projection_path",
        )

    with pytest.raises(ValueError, match="byte limit"):
        trusted_files.read_verified_repo_file(
            repo_root=repo_root,
            relative_path=Path("approved/row.yaml"),
            expected_root=Path("approved"),
            field="projection_path",
            max_bytes=4,
        )

    with pytest.raises(ValueError, match="byte limit"):
        trusted_files.load_verified_yaml_mapping(
            repo_root=repo_root,
            relative_path=Path("approved/row.yaml"),
            expected_root=Path("approved"),
            field="projection_path",
            max_bytes=4,
        )


def test_public_trusted_file_helpers_cover_alias_and_bounds(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    approved = repo_root / "approved"
    approved.mkdir()
    nested = approved / "nested"
    nested.mkdir()
    ok = nested / "row.txt"
    ok.write_text("hello", encoding="utf-8")

    trusted_files.require_non_symlink_path(ok, field="projection_path")
    trusted_files.require_non_symlink_descendants_within_root(
        path=ok, root=approved, field="projection_path"
    )

    off_root = repo_root / "elsewhere.txt"
    off_root.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="outside the approved root"):
        trusted_files.require_non_symlink_descendants_within_root(
            path=off_root, root=approved, field="projection_path"
        )

    alias = approved / "alias"
    alias.symlink_to(nested, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        trusted_files.require_non_symlink_path(alias / "row.txt", field="projection_path")
    with pytest.raises(ValueError, match="symlink"):
        trusted_files.require_non_symlink_descendants_within_root(
            path=alias / "row.txt", root=approved, field="projection_path"
        )

    with pytest.raises(ValueError, match="byte limit"):
        trusted_files.read_verified_repo_text(
            repo_root=repo_root,
            relative_path=Path("approved/nested/row.txt"),
            expected_root=Path("approved"),
            field="projection_path",
            max_bytes=4,
        )

    monkeypatch.setattr(
        trusted_files,
        "read_verified_repo_file",
        lambda **kwargs: b"abcdef",
    )
    with pytest.raises(ValueError, match="byte limit"):
        trusted_files.read_verified_repo_text(
            repo_root=repo_root,
            relative_path=Path("approved/nested/row.txt"),
            expected_root=Path("approved"),
            field="projection_path",
            max_bytes=5,
        )


def test_replay_script_guard_rejects_protected_and_symlink_paths(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    for candidate in (
        Path("/"),
        Path.home(),
        Path.home() / "nsqd-jepa-baselines-child",
        REPO_ROOT,
        REPO_ROOT / "nsqd-jepa-baselines-child",
        PACKET_ROOT,
        PACKET_ROOT / "nsqd-jepa-baselines-child",
    ):
        with pytest.raises(ValueError, match="protected|unsafe ancestor"):
            replay._guard_scratch_dir(candidate)
    with pytest.raises(
        ValueError,
        match="protected|unsafe ancestor|allowlisted system temp root|direct child",
    ):
        replay._guard_scratch_dir(Path("/opt/nsqd-jepa-baselines-replay"))
    assert (
        replay._guard_scratch_dir(Path("/tmp/nsqd-jepa-baselines-replay")).name
        == "nsqd-jepa-baselines-replay"
    )
    safe = Path("/tmp/nsqd-jepa-baselines-replay")
    safe.mkdir(exist_ok=True)
    assert replay._guard_scratch_dir(safe) == safe.resolve()
    alias = tmp_path / "alias"
    alias.symlink_to(Path("/tmp"))
    with pytest.raises(ValueError, match="symlink alias"):
        replay._guard_scratch_dir(alias / "nsqd-jepa-baselines-replay")


def test_replay_script_reads_ollama_manifest_digest_from_configured_service(monkeypatch) -> None:
    import importlib.util
    import io
    import json as json_module
    import types

    spec = importlib.util.spec_from_file_location(
        "replay", REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)

    settings = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(
            base_url="http://127.0.0.1:11434/",
            model="qwen3-embedding:latest",
        )
    )
    monkeypatch.setattr(replay, "load_settings", lambda **_: settings)
    sentinel = object()
    monkeypatch.setattr(replay, "build_local_ollama_embedder", lambda _embeddings: sentinel)

    def ok_payload(*, digest: str, parent_model: str) -> bytes:
        return json_module.dumps(
            {
                "models": [
                    {
                        "name": "qwen3-embedding:latest",
                        "model": "qwen3-embedding:latest",
                        "digest": digest,
                        "details": {"parent_model": parent_model},
                    }
                ]
            }
        ).encode("utf-8")

    def fake_urlopen(url, timeout):
        assert url == "http://127.0.0.1:11434/api/tags"
        assert timeout == 5.0
        return io.BytesIO(
            ok_payload(
                digest=replay.EXPECTED_MANIFEST_DIGEST,
                parent_model=(
                    "/Users/ollama/.ollama/models/blobs/sha256-" + replay.EXPECTED_BLOB_DIGEST
                ),
            )
        )

    monkeypatch.setattr(replay.urllib_request, "urlopen", fake_urlopen)
    embedder, model = replay._prepare_embedder()
    assert embedder is sentinel
    assert model == {
        "manifest_digest": replay.EXPECTED_MANIFEST_DIGEST,
        "blob_digest": replay.EXPECTED_BLOB_DIGEST,
    }

    monkeypatch.setattr(
        replay.urllib_request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(json_module.dumps({"models": []}).encode("utf-8")),
    )
    with pytest.raises(ValueError, match="requested embedding model"):
        replay._prepare_embedder()

    monkeypatch.setattr(
        replay.urllib_request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(
            ok_payload(
                digest="0" * 64,
                parent_model=(
                    "/Users/ollama/.ollama/models/blobs/sha256-" + replay.EXPECTED_BLOB_DIGEST
                ),
            )
        ),
    )
    with pytest.raises(ValueError, match="manifest digest"):
        replay._prepare_embedder()

    monkeypatch.setattr(
        replay.urllib_request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(
            ok_payload(
                digest=replay.EXPECTED_MANIFEST_DIGEST,
                parent_model="",
            )
        ),
    )
    with pytest.raises(ValueError, match="parent blob"):
        replay._prepare_embedder()

    monkeypatch.setattr(
        replay.urllib_request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(
            ok_payload(
                digest=replay.EXPECTED_MANIFEST_DIGEST,
                parent_model="/Users/x/.ollama/models/blobs/sha256-" + ("0" * 64),
            )
        ),
    )
    with pytest.raises(ValueError, match="parent blob digest"):
        replay._prepare_embedder()

    monkeypatch.setattr(
        replay.urllib_request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(b"[]"),
    )
    with pytest.raises(ValueError, match="payload is invalid"):
        replay._prepare_embedder()

    monkeypatch.setattr(
        replay.urllib_request,
        "urlopen",
        lambda _url, timeout: (_ for _ in ()).throw(TimeoutError("boom")),
    )
    with pytest.raises(ValueError, match="tags request failed"):
        replay._prepare_embedder()


def test_required_scratch_runtime_rejects_symlinked_db_and_index_leaves(tmp_path: Path) -> None:
    scratch = tmp_path / "nsqd-jepa-baselines-leaf-check"
    scratch.mkdir()
    real_db = tmp_path / "real.sqlite"
    real_db.write_bytes(b"sqlite")
    db_link = scratch / "nsqd.sqlite"
    db_link.symlink_to(real_db)
    index_dir = scratch / "index"
    index_dir.mkdir()
    with pytest.raises(ValueError, match="symlink"):
        opb._required_scratch_runtime(
            {
                "db_path": str(db_link),
                "index_path": str(index_dir),
                "no_production_writes": True,
                "production_write_paths": [],
            },
            require_exists=True,
        )

    db_link.unlink()
    db_link.write_bytes(b"sqlite")
    real_index = tmp_path / "real-index"
    real_index.mkdir()
    index_link = scratch / "index"
    index_link.rmdir()
    index_link.symlink_to(real_index, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        opb._required_scratch_runtime(
            {
                "db_path": str(db_link),
                "index_path": str(index_link),
                "no_production_writes": True,
                "production_write_paths": [],
            },
            require_exists=True,
        )


def test_load_runtime_store_uses_read_only_sqlite_uri(monkeypatch) -> None:
    calls: list[tuple[object, bool]] = []

    class FakeConnection:
        def execute(self, _query: str):
            class Result:
                def fetchall(self):
                    return []

            return Result()

        def close(self) -> None:
            return None

    def fake_connect(target, *, uri=False):
        calls.append((target, uri))
        return FakeConnection()

    monkeypatch.setattr(opb.sqlite3, "connect", fake_connect)
    runtime = opb._load_runtime_store(Path("/tmp/nsqd-jepa-baselines-readonly/nsqd.sqlite"))
    assert runtime == {"candidate_payloads": {}, "frontier_card_payloads": {}}
    expected_uri = (
        Path("/tmp/nsqd-jepa-baselines-readonly/nsqd.sqlite").resolve(strict=False).as_uri()
    )
    assert calls == [(expected_uri + "?mode=ro", True)]
