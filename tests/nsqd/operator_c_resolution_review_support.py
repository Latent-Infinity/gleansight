from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from tests.nsqd.operator_c_resolution_contracts import (
    EXTRACT_BINDINGS,
    EXTRACT_LOCATIONS,
    EXTRACT_QUOTE_SHA256,
)
from tests.nsqd.operator_c_resolution_review_contracts import (
    APPROVAL_SCOPE,
    AUTHORITY,
    EVIDENCE_ARTIFACTS,
    MANIFEST_SHA256,
    PACKET_DIGEST,
    PRODUCER_IDENTITY,
    PRODUCER_SESSION,
    REVIEW_FIELDS,
    REVIEWED_AT,
    REVIEWER_IDENTITY,
    REVIEWER_SESSION,
    SEAL_FIELDS,
    SOURCE_REPLAY,
    SUMMARY_FIELDS,
    SUMMARY_SHA256,
)
from tests.nsqd.operator_c_resolution_support import validate_resolution_packet

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonMapping = dict[str, JsonValue]


def _json(path: Path) -> JsonMapping:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"review.document.mapping:{path.name}"
    return payload


def _mapping(value: JsonValue) -> JsonMapping:
    assert isinstance(value, dict), "review.value.mapping"
    return value


def _mappings(value: JsonValue) -> list[JsonMapping]:
    assert isinstance(value, list), "review.value.mapping_list"
    return [_mapping(item) for item in value]


def _utc(value: JsonValue) -> str:
    assert isinstance(value, str) and value.endswith("Z"), "review.time.utc"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is UTC, "review.time.utc"
    return value


def _validate_review_identity(summary: JsonMapping) -> None:
    review = _mapping(summary["independent_review"])
    assert set(review) == REVIEW_FIELDS, "review.summary.review.fields.exact"
    assert review["reviewer_identity"] != review["producer_identity"], (
        "review.identity.reviewer_producer.distinct"
    )
    assert review["reviewer_session_id"] != review["producer_session_id"], (
        "review.session.reviewer_producer.distinct"
    )
    assert review["reviewer_identity"] == REVIEWER_IDENTITY, "review.identity.reviewer.exact"
    assert review["producer_identity"] == PRODUCER_IDENTITY, "review.identity.producer.exact"
    assert review["reviewer_session_id"] == REVIEWER_SESSION, "review.session.reviewer.exact"
    assert review["producer_session_id"] == PRODUCER_SESSION, "review.session.producer.exact"
    assert review["reviewer_differs_from_producer"] is True, "review.identity.distinct.true"
    assert review["reviewer_session_differs_from_producer_session"] is True, (
        "review.session.distinct.true"
    )
    assert review["reviewer_agent_type"] == "oracle", "review.identity.agent_type.oracle"
    assert review["reviewer_model"] == "openai/gpt-5.6-sol", "review.identity.model.exact"
    assert _utc(review["reviewed_at_utc"]) == REVIEWED_AT, "review.time.reviewed_at.exact"
    assert review["approval_scope"] == APPROVAL_SCOPE, "review.scope.negative_only"


def _validate_source_replay(summary: JsonMapping) -> None:
    rows = _mappings(summary["source_replay"])
    by_id = {row["source_identity"]: row for row in rows}
    assert set(by_id) == set(SOURCE_REPLAY), "review.source.identities.exact"
    for source_id, expected in SOURCE_REPLAY.items():
        row = by_id[source_id]
        assert row["http_status"] == 200, "review.source.http_status.ok"
        assert row["media_type"] == "application/pdf", "review.source.media_type.pdf"
        assert (row["byte_count"], row["sha256"]) == expected, "review.source.receipt.exact"
        assert row["receipt_exact_match"] is True, "review.source.receipt_match.true"
        assert row["retrieval_uri"] == row["final_url"], "review.source.url.exact"
        _utc(row["observed_at_utc"])


def _validate_passage_replay(summary: JsonMapping) -> None:
    rows = _mappings(summary["passage_replay"])
    by_id = {row["extract_id"]: row for row in rows}
    assert set(by_id) == set(EXTRACT_BINDINGS), "review.passage.identities.exact"
    for extract_id, (stable_id, version, page) in EXTRACT_BINDINGS.items():
        row = by_id[extract_id]
        expected_page, section, _location, printed_page = EXTRACT_LOCATIONS[extract_id]
        assert row["source_identity"] == f"{stable_id}{version}", "review.passage.source.exact"
        assert row["pdf_page"] == page == expected_page, "review.passage.page.exact"
        assert row["section"] == section, "review.passage.section.exact"
        assert row["quote_sha256"] == EXTRACT_QUOTE_SHA256[extract_id], (
            "review.passage.quote_sha256.exact"
        )
        assert row["status"] == "confirmed_at_declared_location", "review.passage.status.confirmed"
        assert ("printed_page" in row) is printed_page, "review.passage.printed_page.exact"
    bridge = by_id["BRIDGE-THREE-REGIME"]
    note = bridge.get("normalization_note")
    assert isinstance(note, str) and "lexical hyphen" in note, "review.passage.hyphen.disclosed"


def _validate_relation_and_controls(summary: JsonMapping) -> None:
    relations = _mapping(summary["relation_analysis"])
    first = _mapping(relations["A_to_bridge"])
    second = _mapping(relations["bridge_to_C"])
    composition = _mapping(relations["composition"])
    assert (first["predicate"], first["direction"], first["polarity"]) == (
        "instantiates_as",
        "A_to_bridge",
        "unsupported",
    ), "review.relation.a_to_bridge.unsupported"
    assert (second["predicate"], second["direction"], second["polarity"]) == (
        "maps_to_or_drives",
        "bridge_to_C",
        "unsupported",
    ), "review.relation.bridge_to_c.unsupported"
    assert composition == {
        "shared_bridge_identity": "latent_limit_order_book_build_up_regime",
        "edge_bridge_endpoint_type": "causal_limit_order_book_latent_build_up_regime",
        "exact_string_identity": False,
        "typed_alias_supported": False,
        "A_to_bridge_supported": False,
        "bridge_to_C_supported": False,
        "composition_justification": "unsupported",
        "accepted_bridge": False,
    }, "review.relation.composition.unsupported"
    controls = _mapping(summary["control_replay"])
    shuffled = _mapping(
        controls["sha256_seeded_shuffled_literature_pair_control_under_identical_query_budget"]
    )
    assert shuffled["derivation_status"] == "unavailable_nonreproducible", (
        "review.control.shuffle.derivation_unavailable"
    )
    assert shuffled["supported_control"] is False, "review.control.shuffle.unsupported"
    assert shuffled["used_as_absence_evidence"] is False, "review.control.shuffle.not_absence"


def _validate_authority(summary: JsonMapping) -> None:
    assert _mapping(summary["authority"]) == AUTHORITY, "review.authority.exact"
    verdict = _mapping(summary["adversarial_verify"])
    assert verdict["verdict"] == "confirmed", "review.verdict.confirmed"
    assert verdict["confidence"] == 0.96, "review.verdict.confidence.exact"
    assert verdict["positive_bridge_supported"] is False, "review.verdict.bridge.false"
    assert verdict["supports_todo_7_advancement"] is False, "review.todo_7.blocked"


def validate_review_summary(root: Path) -> JsonMapping:
    summary_path = root / "review-summary.json"
    summary = _json(summary_path)
    assert set(summary) == SUMMARY_FIELDS, "review.summary.fields.exact"
    assert summary["schema_version"] == 1, "review.summary.schema_version.exact"
    assert summary["packet_digest"] == PACKET_DIGEST, "review.summary.packet_digest.exact"
    assert summary["packet_digest_algorithm"] == "sha256(canonical_json(artifact_sha256))", (
        "review.summary.packet_algorithm.exact"
    )
    assert summary["packet_manifest_sha256"] == MANIFEST_SHA256, (
        "review.summary.manifest_sha256.exact"
    )
    assert _mapping(summary["artifact_sha256"]) == EVIDENCE_ARTIFACTS, (
        "review.summary.artifact_map.exact"
    )
    _validate_review_identity(summary)
    _validate_source_replay(summary)
    _validate_passage_replay(summary)
    _validate_relation_and_controls(summary)
    _validate_authority(summary)
    assert len(_mappings(summary["live_query_replay"])) == 13, "review.live_queries.count.exact"
    assert len(_mappings(summary["findings"])) == 3, "review.findings.count.exact"
    limitations = summary["limitations"]
    assert isinstance(limitations, list) and len(limitations) == 7, "review.limitations.exact"
    cleanup = _mapping(summary["cleanup"])
    assert cleanup["target_present_after"] is False, "review.cleanup.complete"
    assert cleanup["source_or_query_bytes_retained_in_repository"] is False, (
        "review.cleanup.no_repository_bytes"
    )
    assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == SUMMARY_SHA256, (
        "review.summary.sha256.fixed"
    )
    return summary


def validate_review_seal(root: Path, summary: JsonMapping) -> None:
    seal = _json(root / "review-seal.json")
    assert set(seal) == SEAL_FIELDS, "review.seal.fields.exact"
    expected = {
        "schema_version": 1,
        "packet_digest": PACKET_DIGEST,
        "review_summary_sha256": SUMMARY_SHA256,
        "reviewer_identity": REVIEWER_IDENTITY,
        "reviewer_agent_type": "oracle",
        "reviewer_model": "openai/gpt-5.6-sol",
        "reviewer_session_id": REVIEWER_SESSION,
        "producer_identity": PRODUCER_IDENTITY,
        "producer_session_id": PRODUCER_SESSION,
        "reviewed_at_utc": REVIEWED_AT,
        "verdict": "confirmed",
        "approval_scope": APPROVAL_SCOPE,
        "authorization_state": "report_only",
        "accepted_bridge": False,
        "evidence_sufficient": False,
        "technical_review_is_human_acceptance": False,
        "human_acceptance": "not_requested",
        "schema_admission_authorized": False,
        "runtime_authorized": False,
        "todo_7_advancement_authorized": False,
    }
    assert seal == expected, "review.seal.exact"
    assert (
        seal["review_summary_sha256"]
        == hashlib.sha256((root / "review-summary.json").read_bytes()).hexdigest()
    ), "review.seal.summary_sha256.match"
    assert (
        seal["reviewer_identity"] == _mapping(summary["independent_review"])["reviewer_identity"]
    ), "review.seal.reviewer.match"
    _utc(seal["reviewed_at_utc"])


def validate_review_chain(root: Path) -> str:
    packet_digest = validate_resolution_packet(root)
    assert packet_digest == PACKET_DIGEST, "review.packet_digest.fixed"
    assert hashlib.sha256((root / "packet-manifest.json").read_bytes()).hexdigest() == (
        MANIFEST_SHA256
    ), "review.manifest_sha256.fixed"
    summary = validate_review_summary(root)
    validate_review_seal(root, summary)
    return SUMMARY_SHA256
