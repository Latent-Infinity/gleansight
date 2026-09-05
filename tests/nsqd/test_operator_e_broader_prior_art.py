from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from nsqd.domain.operator_e import (
    bind_operator_e_broader_prior_art_evidence,
    bind_operator_e_inventory,
    operator_e_broader_prior_art_packet_digest,
    validate_operator_e_broader_prior_art_evidence,
)

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
BROADER_NAME = "operator-e-broader-prior-art.json"
SOURCE_CANDIDATE_SHA256 = "c2fee6a3a925dd8c55812c533b588972bd98ee036ed13481ac6a573b362f3783"
EXPECTED_BINDINGS = {
    "E-REPORT-01": "9bb6044553a17738cea566c0f2c4563094d39e1353b4d2163d764a8fda3f2aa0",
    "E-REPORT-02": "e8d0d1dc3e4b7c79f1374b3b2a364fd5f9e5080452acaef8922890bfb25e5084",
    "E-REPORT-03": "b3edc59a50717fb3347cf3f34c04bdca9c87d3a7cb41c0e5b297a892fd02c415",
}
ALLOWED_CONCLUSIONS = {
    "strong_component_overlap_combination_unresolved",
    "strong_mechanism_overlap_combination_unresolved",
}


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _approved_records(packet: dict[str, Any]) -> dict[str, Any]:
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
    return records


def test_committed_broader_prior_art_packet_is_digest_bound_and_report_only() -> None:
    packet = _json(JEPA_ROOT / BROADER_NAME)
    assert packet["packet_kind"] == "operator_e_broader_prior_art_evidence"
    assert packet["authorization_state"] == "report_only"
    assert packet["runtime_authorized"] is False
    assert packet["evidence_sufficient"] is False
    assert packet["algorithm_identity"] == "not_run"
    assert packet["candidate_combinations"] == []
    assert packet["candidate_outputs"] == []
    assert packet["corpus_fact_writes"] == 0
    assert packet["sealed_at_utc"] == "2026-09-03T08:26:14Z"
    assert packet["cutoff_utc"] == "2026-09-03T00:00:00Z"
    assert packet["source_candidate_packet"] == {
        "path": "operator-e-report-only-candidates.json",
        "sha256": SOURCE_CANDIDATE_SHA256,
        "artifact_bindings": [
            {
                "artifact_id": "E-REPORT-01",
                "artifact_hash": EXPECTED_BINDINGS["E-REPORT-01"],
                "source_idea_id": "JEPA-IDEA-01",
            },
            {
                "artifact_id": "E-REPORT-02",
                "artifact_hash": EXPECTED_BINDINGS["E-REPORT-02"],
                "source_idea_id": "JEPA-IDEA-02",
            },
            {
                "artifact_id": "E-REPORT-03",
                "artifact_hash": EXPECTED_BINDINGS["E-REPORT-03"],
                "source_idea_id": "JEPA-IDEA-03",
            },
        ],
    }
    assert (
        packet["source_snapshot_id"]
        == "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
    )
    assert packet["corpus_version"] == 11
    assert len(packet["primary_sources"]) == 13
    assert len({row["stable_id"] for row in packet["primary_sources"]}) == 13
    assert {row["artifact_id"] for row in packet["candidate_assessments"]} == set(EXPECTED_BINDINGS)
    for assessment in packet["candidate_assessments"]:
        assert assessment["artifact_hash"] == EXPECTED_BINDINGS[assessment["artifact_id"]]
        assert (
            assessment["source_candidate_packet_path"] == "operator-e-report-only-candidates.json"
        )
        assert assessment["source_candidate_packet_sha256"] == SOURCE_CANDIDATE_SHA256
        assert assessment["conclusion"] in ALLOWED_CONCLUSIONS
        assert assessment["novelty_claim"] == "not_established"
        assert assessment["absence_interpretation"] == "bounded absence is not proof of novelty"
        assert assessment["nearest_prior_combinations"]
        for combo in assessment["nearest_prior_combinations"]:
            assert combo["source_ids"]
            assert set(combo["source_ids"]) <= {
                row["stable_id"] for row in packet["primary_sources"]
            }
    assert packet["search_protocol"]["query_count"] == 3
    assert packet["search_protocol"]["unique_primary_record_count"] == 13
    assert packet["search_protocol"]["novelty_claim"] == "not_established"
    assert (
        packet["search_protocol"]["absence_interpretation"]
        == "bounded absence is not proof of novelty"
    )
    assert packet["packet_digest"] == operator_e_broader_prior_art_packet_digest(packet)
    validated = validate_operator_e_broader_prior_art_evidence(packet)
    assert validated["runtime_authorized"] is False


def test_committed_operator_e_packet_binds_broader_prior_art_without_authorizing_e() -> None:
    operator_e_packet = _yaml(PACKET_ROOT / "operator-e.yaml")
    records = _approved_records(operator_e_packet)
    inventory = bind_operator_e_inventory(operator_e_packet, approved_records=records)
    broader = _json(JEPA_ROOT / BROADER_NAME)
    bound = bind_operator_e_broader_prior_art_evidence(inventory, broader)
    assert inventory["candidate_combinations"] == []
    assert inventory["candidate_outputs"] == []
    assert inventory["algorithm_identity"] == "not_run"
    assert bound["candidate_combinations"] == []
    assert bound["candidate_outputs"] == []
    assert bound["algorithm_identity"] == "not_run"
    assert bound["runtime_authorized"] is False
    assert bound["evidence_sufficient"] is False
    assert bound["primary_source_count"] == 13
    assert bound["report_only_artifact_ids"] == ["E-REPORT-01", "E-REPORT-02", "E-REPORT-03"]


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda packet: packet.__setitem__("runtime_authorized", True), "runtime_authorized"),
        (lambda packet: packet.__setitem__("evidence_sufficient", True), "evidence_sufficient"),
        (lambda packet: packet.__setitem__("packet_digest", "0" * 64), "packet_digest"),
        (
            lambda packet: packet["source_candidate_packet"].__setitem__("sha256", "0" * 64),
            "sha256",
        ),
        (
            lambda packet: packet["source_candidate_packet"]["artifact_bindings"][0].__setitem__(
                "artifact_hash", "0" * 64
            ),
            "artifact_hash",
        ),
        (
            lambda packet: packet["primary_sources"][0].__setitem__("stable_id", "bad-id"),
            "stable_id",
        ),
        (
            lambda packet: packet["primary_sources"][0].__setitem__(
                "primary_url", "https://wrong.example"
            ),
            "primary_url",
        ),
        (
            lambda packet: packet["primary_sources"][0].__setitem__(
                "submitted_at_utc", "2026-01-21"
            ),
            "submitted_at_utc",
        ),
        (
            lambda packet: packet["candidate_assessments"][0].__setitem__("conclusion", "novel"),
            "conclusion",
        ),
        (
            lambda packet: packet["forbidden_inferences"].append("novelty is established"),
            "forbidden_inferences",
        ),
    ],
)
def test_broader_prior_art_packet_rejects_tampering(mutator, match: str) -> None:
    packet = _json(JEPA_ROOT / BROADER_NAME)
    tampered = copy.deepcopy(packet)
    mutator(tampered)
    if match != "packet_digest":
        tampered["packet_digest"] = operator_e_broader_prior_art_packet_digest(tampered)
    with pytest.raises(ValueError, match=match):
        validate_operator_e_broader_prior_art_evidence(tampered)


def test_broader_prior_art_inventory_declaration_rejects_authorization_and_count_drift() -> None:
    packet = _yaml(PACKET_ROOT / "operator-e.yaml")
    records = _approved_records(packet)
    inventory = bind_operator_e_inventory(packet, approved_records=records)
    broader = _json(JEPA_ROOT / BROADER_NAME)

    tampered_inventory = copy.deepcopy(inventory)
    tampered_inventory["broader_prior_art_evidence"]["passed_to_diverge"] = True
    with pytest.raises(ValueError, match="must not be passed to DivergeUseCase"):
        bind_operator_e_broader_prior_art_evidence(tampered_inventory, broader)

    tampered_inventory = copy.deepcopy(inventory)
    tampered_inventory["broader_prior_art_evidence"][
        "human_evidence_decision_authorizes_operator_e"
    ] = True
    with pytest.raises(ValueError, match="does not authorize Operator E"):
        bind_operator_e_broader_prior_art_evidence(tampered_inventory, broader)

    tampered_inventory = copy.deepcopy(inventory)
    tampered_inventory["broader_prior_art_evidence"]["primary_source_count"] = "13"
    with pytest.raises(ValueError, match="primary_source_count"):
        bind_operator_e_broader_prior_art_evidence(tampered_inventory, broader)


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda packet: packet.__setitem__("schema_version", 2), "schema_version"),
        (
            lambda packet: packet.__setitem__("algorithm_identity", "operator-e/1"),
            "algorithm_identity",
        ),
        (
            lambda packet: packet.__setitem__("candidate_combinations", [{"x": 1}]),
            "candidate_combinations",
        ),
        (lambda packet: packet.__setitem__("candidate_outputs", [{"x": 1}]), "candidate_outputs"),
        (lambda packet: packet.__setitem__("corpus_fact_writes", 1), "corpus_fact_writes"),
        (lambda packet: packet["search_protocol"].__setitem__("query_count", 4), "query_count"),
        (
            lambda packet: packet["search_protocol"].__setitem__(
                "failed_librarian_sessions_counted", True
            ),
            "failed_librarian_sessions_counted",
        ),
        (
            lambda packet: packet["search_protocol"].__setitem__("unique_primary_record_count", 12),
            "unique_primary_record_count",
        ),
        (
            lambda packet: packet.__setitem__("primary_sources", packet["primary_sources"][:12]),
            "primary_sources",
        ),
        (lambda packet: packet["primary_sources"][0].__setitem__("doi", "bad-doi"), "doi"),
        (lambda packet: packet["primary_sources"][0].__setitem__("authors", []), "authors"),
        (
            lambda packet: packet["primary_sources"][0].__setitem__(
                "evidence_locator", "full text"
            ),
            "evidence_locator",
        ),
        (
            lambda packet: packet["candidate_assessments"][0].__setitem__(
                "nearest_prior_combinations", []
            ),
            "nearest_prior_combinations",
        ),
        (
            lambda packet: packet["candidate_assessments"][0]["nearest_prior_combinations"][
                0
            ].__setitem__("source_ids", ["bad-id"]),
            "source_ids",
        ),
        (
            lambda packet: packet["candidate_assessments"][0]["nearest_prior_combinations"][
                0
            ].__setitem__("overlap_summary", " "),
            "overlap_summary",
        ),
        (
            lambda packet: packet["candidate_assessments"][0].__setitem__(
                "remaining_question", " "
            ),
            "remaining_question",
        ),
        (
            lambda packet: packet["candidate_assessments"][0].__setitem__(
                "narrowed_overlap_conclusion", " "
            ),
            "narrowed_overlap_conclusion",
        ),
        (
            lambda packet: packet["primary_sources"][0].__setitem__(
                "evidence_summary", "Resealed semantic drift"
            ),
            "packet_digest",
        ),
        (
            lambda packet: packet["search_protocol"]["query_log"][0].__setitem__(
                "query_text", "Resealed query drift"
            ),
            "packet_digest",
        ),
        (
            lambda packet: packet["known_limitations"].__setitem__(0, "bounded search only"),
            "known_limitations",
        ),
    ],
)
def test_broader_prior_art_packet_rejects_additional_fail_closed_drift(mutator, match: str) -> None:
    packet = _json(JEPA_ROOT / BROADER_NAME)
    tampered = copy.deepcopy(packet)
    mutator(tampered)
    tampered["packet_digest"] = operator_e_broader_prior_art_packet_digest(tampered)
    with pytest.raises(ValueError, match=match):
        validate_operator_e_broader_prior_art_evidence(tampered)


def test_inventory_rejects_invalid_broader_prior_art_attachment_shape() -> None:
    packet = _yaml(PACKET_ROOT / "operator-e.yaml")
    records = _approved_records(packet)
    tampered = copy.deepcopy(packet)
    tampered["broader_prior_art_evidence"]["artifact_ids"] = ["E-REPORT-01"]
    with pytest.raises(ValueError, match="artifact_ids"):
        bind_operator_e_inventory(tampered, approved_records=records)

    tampered = copy.deepcopy(packet)
    tampered["broader_prior_art_evidence"]["source_candidate_sha256"] = "bad"
    with pytest.raises(ValueError, match="source_candidate_sha256"):
        bind_operator_e_inventory(tampered, approved_records=records)


def test_broader_prior_art_binder_rejects_inventory_and_packet_drift() -> None:
    packet = _yaml(PACKET_ROOT / "operator-e.yaml")
    records = _approved_records(packet)
    inventory = bind_operator_e_inventory(packet, approved_records=records)
    broader = _json(JEPA_ROOT / BROADER_NAME)

    bad_inventory = copy.deepcopy(inventory)
    bad_inventory["runtime_authorized"] = True
    with pytest.raises(ValueError, match="runtime_authorized"):
        bind_operator_e_broader_prior_art_evidence(bad_inventory, broader)

    bad_inventory = copy.deepcopy(inventory)
    bad_inventory["candidate_outputs"] = [{"candidate_id": "invented"}]
    with pytest.raises(ValueError, match="candidate_outputs"):
        bind_operator_e_broader_prior_art_evidence(bad_inventory, broader)

    bad_inventory = copy.deepcopy(inventory)
    bad_inventory["broader_prior_art_evidence"]["source_packet_digest"] = "0" * 64
    with pytest.raises(ValueError, match="source_packet_digest"):
        bind_operator_e_broader_prior_art_evidence(bad_inventory, broader)

    bad_inventory = copy.deepcopy(inventory)
    bad_inventory["broader_prior_art_evidence"]["source_candidate_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source_candidate_sha256"):
        bind_operator_e_broader_prior_art_evidence(bad_inventory, broader)

    bad_inventory = copy.deepcopy(inventory)
    bad_inventory["broader_prior_art_evidence"]["primary_source_count"] = 12
    with pytest.raises(ValueError, match="primary_source_count"):
        bind_operator_e_broader_prior_art_evidence(bad_inventory, broader)
