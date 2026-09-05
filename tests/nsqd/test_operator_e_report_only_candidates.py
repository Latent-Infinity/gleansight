from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from nsqd.domain.diverge import require_operator
from nsqd.domain.operator_baselines import report_only_operator_e_candidate_hash
from nsqd.domain.operator_e import (
    OPERATOR_E_ATYPICALITY_INTERPRETATION,
    bind_operator_e_inventory,
    bind_operator_e_report_only_candidates,
)
from nsqd.domain.snapshot import canonical_json, sha256_hex

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
PROJECTION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reviews"
    / "nsqd-projection-review-2026-08-28"
    / "final"
)
APPROVED_NSQD_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "approved" / "nsqd"
)
JEPA_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
)
DIGEST = "a" * 64
RESULTS_DIGEST = "b" * 64
SNAPSHOT_ID = "c" * 64
CO_OCCURRENCE_ID = "d" * 64
SOURCE = "../nsqd-jepa-ideas-gaps-2026-09-01/operator-e-report-only-candidates.json"


def _record(record_id: str, *, domain_policy_id: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": "corpus-paper-paraphrase",
        "review_status": "approved",
        "domain_policy_id": domain_policy_id,
        "title": record_id,
        "source_paper_id": f"id:{record_id}",
    }


APPROVED = {
    "DATA-NSQD-03": _record("DATA-NSQD-03", domain_policy_id="finance/1"),
    "N11-FIN-01": _record("N11-FIN-01", domain_policy_id="finance/1"),
    "DATA-NSQD-04": _record("DATA-NSQD-04", domain_policy_id="optimization/1"),
    "N11-OPT-01": _record("N11-OPT-01", domain_policy_id="optimization/1"),
}


def _declaration(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": SOURCE,
        "source_packet_digest": DIGEST,
        "source_content_digest": sha256_hex(canonical_json(_candidates())),
        "review_summary_packet_digest": DIGEST,
        "artifact_ids": ["E-REPORT-01"],
        "passed_to_diverge": False,
        "human_usefulness_review_authorizes_operator_e": False,
    }
    payload.update(overrides)
    return payload


def _packet(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operator": "E",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": False,
        "approved_component_inventory": {
            "finance/1": ["DATA-NSQD-03", "N11-FIN-01"],
            "optimization/1": ["DATA-NSQD-04", "N11-OPT-01"],
        },
        "candidate_combinations": [],
        "candidate_outputs": [],
        "tracks": {
            "same_policy": {"policy_rule": "one domain_policy_id"},
            "cross_policy": {"policy_rule": "bind source and target"},
        },
        "report_only_candidate_artifacts": _declaration(),
    }
    payload.update(overrides)
    return payload


def _candidate(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact_id": "E-REPORT-01",
        "source_idea_id": "JEPA-IDEA-01",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": False,
        "human_usefulness_score": None,
        "title": "Report-only test candidate",
        "component_ids": ["N11-FIN-01"],
        "supporting_fact_ids": ["JEPA-FACT-01"],
        "co_occurrence_snapshot_id": CO_OCCURRENCE_ID,
        "source_snapshot_id": SNAPSHOT_ID,
        "corpus_version": 11,
        "atypicality": {"interpretation": OPERATOR_E_ATYPICALITY_INTERPRETATION},
        "mechanistic_bridge": "Test-only mechanistic bridge.",
        "falsifiable_test": {
            "design": "Test-only design.",
            "primary_metric": "test metric",
            "secondary_metrics": ["secondary metric"],
            "failure_condition": "Reject on test failure.",
        },
        "prior_art_status": "partial_overlap",
        "nearest_prior_combinations": [],
    }
    payload.update(overrides)
    if "artifact_hash" not in overrides:
        payload["artifact_hash"] = report_only_operator_e_candidate_hash(payload)
    return payload


def _candidates(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "packet_kind": "operator_e_report_only_candidates",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": False,
        "derived_at_utc": "2026-09-02T06:45:00Z",
        "source_results_path": "results.json",
        "source_results_sha256": RESULTS_DIGEST,
        "source_snapshot_id": SNAPSHOT_ID,
        "corpus_version": 11,
        "candidates": [_candidate()],
    }
    payload.update(overrides)
    return payload


def _review(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "runtime_authorized": False,
        "evidence_sufficient": False,
        "operator_activation_requested": False,
        "packet_digest": DIGEST,
        "artifact_sha256": {
            "operator-e-report-only-candidates.json": DIGEST,
            "results.json": RESULTS_DIGEST,
        },
        "accounting_revision": {
            "human_usefulness_review_status": "completed",
            "operator_e_authorization_state": "unauthorized",
        },
        "human_usefulness_review": {
            "packet_status": "completed",
            "descriptive_only": True,
            "statistical_significance_inference": False,
            "by_operator": {
                "A": {"mean_score": 1.666667},
                "E": {"mean_score": 1.0},
            },
        },
    }
    payload.update(overrides)
    return payload


def _inventory(**overrides: object) -> dict[str, Any]:
    return bind_operator_e_inventory(_packet(**overrides), approved_records=APPROVED)


def test_report_only_candidates_bind_without_authorizing_operator_e() -> None:
    bound = bind_operator_e_report_only_candidates(
        _inventory(),
        _candidates(),
        review_summary=_review(),
    )
    assert bound["report_only_artifact_ids"] == ["E-REPORT-01"]
    assert bound["passed_to_diverge"] is False
    assert bound["human_usefulness_review_status"] == "completed"
    assert bound["human_usefulness_review_authorizes_operator_e"] is False
    assert bound["candidate_combinations"] == []
    assert bound["candidate_outputs"] == []
    assert bound["algorithm_identity"] == "not_run"
    assert bound["evidence_sufficient"] is False
    assert bound["runtime_authorized"] is False
    with pytest.raises(ValueError, match="not enabled by composition"):
        require_operator("E", enabled_operators=frozenset({"A", "B"}))


def test_higher_operator_a_usefulness_does_not_authorize_operator_e() -> None:
    bound = bind_operator_e_report_only_candidates(
        _inventory(),
        _candidates(),
        review_summary=_review(),
    )
    review = _review()["human_usefulness_review"]
    assert review["by_operator"]["A"]["mean_score"] > review["by_operator"]["E"]["mean_score"]
    assert bound["runtime_authorized"] is False
    assert bound["evidence_sufficient"] is False


def test_inventory_rejects_authorizing_report_only_candidate_declaration() -> None:
    with pytest.raises(ValueError, match="does not authorize Operator E"):
        _inventory(
            report_only_candidate_artifacts=_declaration(
                human_usefulness_review_authorizes_operator_e=True
            )
        )
    with pytest.raises(ValueError, match="must not be passed to DivergeUseCase"):
        _inventory(report_only_candidate_artifacts=_declaration(passed_to_diverge=True))
    with pytest.raises(ValueError, match="duplicate artifact_id"):
        _inventory(
            report_only_candidate_artifacts=_declaration(
                artifact_ids=["E-REPORT-01", "E-REPORT-01"]
            )
        )
    with pytest.raises(ValueError, match="source_packet_digest must be a lowercase SHA-256"):
        _inventory(
            report_only_candidate_artifacts=_declaration(source_packet_digest="not-a-digest")
        )
    with pytest.raises(ValueError, match="artifact_ids is required"):
        _inventory(report_only_candidate_artifacts=_declaration(artifact_ids=[]))
    with pytest.raises(ValueError, match="report_only_candidate_artifacts is required"):
        bind_operator_e_inventory(
            _packet(report_only_candidate_artifacts="missing"),
            approved_records=APPROVED,
        )


def test_report_only_candidates_reject_authorization_and_generation_leaks() -> None:
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_e_report_only_candidates(
            {**_inventory(), "runtime_authorized": True},
            _candidates(),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="evidence_sufficient must be false"):
        bind_operator_e_report_only_candidates(
            {**_inventory(), "evidence_sufficient": True},
            _candidates(),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="candidate_combinations must be an empty list"):
        bind_operator_e_report_only_candidates(
            {**_inventory(), "candidate_combinations": [{"components": ["N11-FIN-01"]}]},
            _candidates(),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="candidate_outputs must be an empty list"):
        bind_operator_e_report_only_candidates(
            {**_inventory(), "candidate_outputs": [{"candidate_id": "invented"}]},
            _candidates(),
            review_summary=_review(),
        )
    missing = _inventory()
    missing.pop("report_only_candidate_artifacts")
    with pytest.raises(ValueError, match="report_only_candidate_artifacts is required"):
        bind_operator_e_report_only_candidates(missing, _candidates(), review_summary=_review())


def test_pending_usefulness_review_still_does_not_authorize_operator_e() -> None:
    pending = _review()
    pending["accounting_revision"]["human_usefulness_review_status"] = "pending"
    pending["human_usefulness_review"] = {
        "packet_status": "pending",
        "descriptive_only": False,
        "statistical_significance_inference": True,
    }
    bound = bind_operator_e_report_only_candidates(
        _inventory(),
        _candidates(),
        review_summary=pending,
    )
    assert bound["human_usefulness_review_status"] == "pending"
    assert bound["runtime_authorized"] is False
    assert bound["human_usefulness_review_authorizes_operator_e"] is False


def test_report_only_candidates_reject_packet_and_review_drift() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(schema_version=2),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="packet_kind"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(packet_kind="evidence_report"),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="report_only"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(authorization_state="authorized"),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(runtime_authorized=True),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="evidence_sufficient must be false"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(evidence_sufficient=True),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=_review(runtime_authorized=True),
        )
    with pytest.raises(ValueError, match="evidence_sufficient must be false"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=_review(evidence_sufficient=True),
        )
    with pytest.raises(ValueError, match="candidates is required"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="artifact_ids do not match"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(artifact_id="E-REPORT-99")]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="review_summary_packet_digest does not match"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=_review(packet_digest="b" * 64),
        )
    wrong_source_digest = _review()
    wrong_source_digest["artifact_sha256"]["operator-e-report-only-candidates.json"] = "e" * 64
    with pytest.raises(ValueError, match="named candidate packet"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=wrong_source_digest,
        )
    with pytest.raises(ValueError, match="canonical candidate packet"):
        bind_operator_e_report_only_candidates(
            _inventory(
                report_only_candidate_artifacts=_declaration(source_content_digest="e" * 64)
            ),
            _candidates(),
            review_summary=_review(),
        )
    authorized_review = _review()
    authorized_review["accounting_revision"]["operator_e_authorization_state"] = "authorized"
    with pytest.raises(ValueError, match="does not authorize Operator E"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=authorized_review,
        )
    requested = _review(operator_activation_requested=True)
    with pytest.raises(ValueError, match="does not authorize Operator E"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=requested,
        )
    inferential = _review()
    inferential["human_usefulness_review"]["descriptive_only"] = False
    with pytest.raises(ValueError, match="descriptive only"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=inferential,
        )
    significant = _review()
    significant["human_usefulness_review"]["statistical_significance_inference"] = True
    with pytest.raises(ValueError, match="descriptive only"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(),
            review_summary=significant,
        )


def test_report_only_candidates_reject_artifact_field_leaks() -> None:
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(runtime_authorized=True)]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="evidence_sufficient must be false"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(evidence_sufficient=True)]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="human_usefulness_score must remain null"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(human_usefulness_score=1)]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="report_only"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(authorization_state="authorized")]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="not in the Operator E inventory"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(component_ids=["N11-FIN-99"])]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="canonical rarity contract"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(
                candidates=[_candidate(atypicality={"interpretation": "novelty and value"})]
            ),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="duplicate artifact_id"):
        bind_operator_e_report_only_candidates(
            _inventory(
                report_only_candidate_artifacts=_declaration(
                    artifact_ids=["E-REPORT-01", "E-REPORT-02"]
                )
            ),
            _candidates(candidates=[_candidate(), _candidate()]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="duplicate component_id"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(component_ids=["N11-FIN-01", "N11-FIN-01"])]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="nearest_prior_combinations is required"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(nearest_prior_combinations="none")]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="source_snapshot_id"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(source_snapshot_id="e" * 64)]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="corpus_version"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(corpus_version=12)]),
            review_summary=_review(),
        )
    with pytest.raises(ValueError, match="canonical candidate content"):
        bind_operator_e_report_only_candidates(
            _inventory(),
            _candidates(candidates=[_candidate(artifact_hash="0" * 64)]),
            review_summary=_review(),
        )


def test_committed_operator_e_packet_binds_jepa_report_only_candidates() -> None:
    packet = yaml.safe_load((PACKET_ROOT / "operator-e.yaml").read_text(encoding="utf-8"))
    records: dict[str, Any] = {}
    for record_id in packet["approved_component_inventory"]["finance/1"]:
        path = (
            APPROVED_NSQD_ROOT / "gamma-fragility.yaml"
            if record_id == "DATA-NSQD-03"
            else PROJECTION_ROOT / f"{record_id}.yaml"
        )
        records[record_id] = yaml.safe_load(path.read_text(encoding="utf-8"))
    for record_id in packet["approved_component_inventory"]["optimization/1"]:
        path = (
            APPROVED_NSQD_ROOT / "paper-a.yaml"
            if record_id == "DATA-NSQD-04"
            else PROJECTION_ROOT / f"{record_id}.yaml"
        )
        records[record_id] = yaml.safe_load(path.read_text(encoding="utf-8"))
    inventory = bind_operator_e_inventory(packet, approved_records=records)
    candidates = json.loads(
        (JEPA_ROOT / "operator-e-report-only-candidates.json").read_text(encoding="utf-8")
    )
    summary = json.loads((JEPA_ROOT / "review-summary.json").read_text(encoding="utf-8"))
    declaration = packet["report_only_candidate_artifacts"]
    assert declaration["source"] == SOURCE
    assert (
        declaration["source_packet_digest"]
        == summary["artifact_sha256"]["operator-e-report-only-candidates.json"]
    )
    assert declaration["review_summary_packet_digest"] == summary["packet_digest"]
    assert declaration["source_content_digest"] == sha256_hex(canonical_json(candidates))
    assert declaration["passed_to_diverge"] is False
    assert declaration["human_usefulness_review_authorizes_operator_e"] is False
    bound = bind_operator_e_report_only_candidates(
        inventory,
        candidates,
        review_summary=summary,
    )
    assert bound["report_only_artifact_ids"] == ["E-REPORT-01", "E-REPORT-02", "E-REPORT-03"]
    assert packet["candidate_combinations"] == []
    assert packet["candidate_outputs"] == []
    assert packet["algorithm_identity"] == "operator-e-atypical-combination/1"
    assert packet["packet_kind"] == "evidence_plan"
    assert bound["runtime_authorized"] is False
    assert bound["evidence_sufficient"] is False
    mutated = copy.deepcopy(summary)
    mutated["accounting_revision"]["operator_e_authorization_state"] = "authorized"
    with pytest.raises(ValueError, match="does not authorize Operator E"):
        bind_operator_e_report_only_candidates(
            inventory,
            candidates,
            review_summary=mutated,
        )

    resealed_candidate_drift = copy.deepcopy(candidates)
    resealed_candidate_drift["candidates"][0]["title"] = "Resealed semantic drift"
    resealed_candidate_drift["candidates"][0]["artifact_hash"] = (
        report_only_operator_e_candidate_hash(resealed_candidate_drift["candidates"][0])
    )
    with pytest.raises(ValueError, match="canonical candidate packet"):
        bind_operator_e_report_only_candidates(
            inventory,
            resealed_candidate_drift,
            review_summary=summary,
        )

    source_drift = copy.deepcopy(candidates)
    source_drift["source_results_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="named results packet"):
        bind_operator_e_report_only_candidates(
            inventory,
            source_drift,
            review_summary=summary,
        )
