from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Final

import pytest

from tests.nsqd.operator_c_resolution_review_contracts import (
    EVIDENCE_ARTIFACTS,
    PRODUCER_IDENTITY,
    PRODUCER_SESSION,
    REVIEWER_IDENTITY,
    REVIEWER_SESSION,
    SUMMARY_SHA256,
)
from tests.nsqd.operator_c_resolution_review_support import validate_review_chain
from tests.nsqd.operator_c_resolution_test_support import (
    PACKET_ROOT,
    JsonValue,
    TamperCase,
    _set_value,
)

SUMMARY_TAMPER_CASES: Final = (
    TamperCase(
        "wrong_packet_digest",
        "review-summary.json",
        ("packet_digest",),
        "0" * 64,
        "review.summary.packet_digest.exact",
    ),
    TamperCase(
        "wrong_manifest_digest",
        "review-summary.json",
        ("packet_manifest_sha256",),
        "0" * 64,
        "review.summary.manifest_sha256.exact",
    ),
    TamperCase(
        "wrong_artifact_digest",
        "review-summary.json",
        ("artifact_sha256", "README.md"),
        "0" * 64,
        "review.summary.artifact_map.exact",
    ),
    TamperCase(
        "source_replay_tamper",
        "review-summary.json",
        ("source_replay", 0, "byte_count"),
        1,
        "review.source.receipt.exact",
    ),
    TamperCase(
        "relation_tamper",
        "review-summary.json",
        ("relation_analysis", "A_to_bridge", "predicate"),
        "supports",
        "review.relation.a_to_bridge.unsupported",
    ),
    TamperCase(
        "reviewer_identity_collision",
        "review-summary.json",
        ("independent_review", "reviewer_identity"),
        PRODUCER_IDENTITY,
        "review.identity.reviewer_producer.distinct",
    ),
    TamperCase(
        "reviewer_session_collision",
        "review-summary.json",
        ("independent_review", "reviewer_session_id"),
        PRODUCER_SESSION,
        "review.session.reviewer_producer.distinct",
    ),
    TamperCase(
        "producer_identity_collision",
        "review-summary.json",
        ("independent_review", "producer_identity"),
        REVIEWER_IDENTITY,
        "review.identity.reviewer_producer.distinct",
    ),
    TamperCase(
        "producer_session_collision",
        "review-summary.json",
        ("independent_review", "producer_session_id"),
        REVIEWER_SESSION,
        "review.session.reviewer_producer.distinct",
    ),
    TamperCase(
        "non_utc_review_time",
        "review-summary.json",
        ("independent_review", "reviewed_at_utc"),
        "2026-09-10T02:28:53+01:00",
        "review.time.utc",
    ),
    TamperCase(
        "authority_escalation",
        "review-summary.json",
        ("authority", "runtime_authorized"),
        True,
        "review.authority.exact",
    ),
    TamperCase(
        "todo_7_advancement",
        "review-summary.json",
        ("adversarial_verify", "supports_todo_7_advancement"),
        True,
        "review.todo_7.blocked",
    ),
    TamperCase(
        "summary_content_tamper",
        "review-summary.json",
        ("findings", 0, "severity"),
        "critical",
        "review.summary.sha256.fixed",
    ),
)

SEAL_TAMPER_CASES: Final = (
    TamperCase(
        "seal_summary_digest",
        "review-seal.json",
        ("review_summary_sha256",),
        "0" * 64,
        "review.seal.exact",
    ),
    TamperCase(
        "seal_packet_digest", "review-seal.json", ("packet_digest",), "0" * 64, "review.seal.exact"
    ),
    TamperCase(
        "seal_authority_escalation",
        "review-seal.json",
        ("schema_admission_authorized",),
        True,
        "review.seal.exact",
    ),
    TamperCase(
        "seal_reviewer_collision",
        "review-seal.json",
        ("reviewer_identity",),
        PRODUCER_IDENTITY,
        "review.seal.exact",
    ),
)


def _tampered_review(tmp_path: Path, case: TamperCase) -> Path:
    packet = tmp_path / case.name
    shutil.copytree(PACKET_ROOT, packet)
    artifact = packet / case.artifact
    payload: JsonValue = json.loads(artifact.read_text(encoding="utf-8"))
    _set_value(payload, case.path, case.replacement)
    artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if case.artifact == "review-summary.json":
        seal = json.loads((packet / "review-seal.json").read_text(encoding="utf-8"))
        assert isinstance(seal, dict)
        seal["review_summary_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        (packet / "review-seal.json").write_text(
            json.dumps(seal, indent=2) + "\n", encoding="utf-8"
        )
    return packet


def test_detached_review_chain_is_valid_and_acyclic() -> None:
    assert validate_review_chain(PACKET_ROOT) == SUMMARY_SHA256
    manifest = json.loads((PACKET_ROOT / "packet-manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_sha256"] == EVIDENCE_ARTIFACTS
    assert {path.name for path in PACKET_ROOT.iterdir()} == {
        *EVIDENCE_ARTIFACTS,
        "packet-manifest.json",
        "review-summary.json",
        "review-seal.json",
    }


@pytest.mark.parametrize("case", SUMMARY_TAMPER_CASES, ids=lambda case: case.name)
def test_rehashed_review_summary_tampering_fails_closed(tmp_path: Path, case: TamperCase) -> None:
    packet = _tampered_review(tmp_path, case)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_review_chain(packet)


@pytest.mark.parametrize("case", SEAL_TAMPER_CASES, ids=lambda case: case.name)
def test_review_seal_tampering_fails_closed(tmp_path: Path, case: TamperCase) -> None:
    packet = _tampered_review(tmp_path, case)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_review_chain(packet)


def test_evidence_member_tampering_fails_closed(tmp_path: Path) -> None:
    packet = tmp_path / "evidence-member"
    shutil.copytree(PACKET_ROOT, packet)
    (packet / "README.md").write_bytes((packet / "README.md").read_bytes() + b"\n")
    with pytest.raises(
        AssertionError, match="^resolution.manifest.artifact_sha256.match:README.md$"
    ):
        validate_review_chain(packet)


def test_source_extract_tampering_fails_closed(tmp_path: Path) -> None:
    packet = tmp_path / "source"
    shutil.copytree(PACKET_ROOT, packet)
    extracts = (packet / "source-extracts.jsonl").read_text(encoding="utf-8")
    (packet / "source-extracts.jsonl").write_text(
        extracts.replace("A-SOFT-CODEBOOK", "A-TAMPERED", 1), encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="^resolution.extract.identity.exact$"):
        validate_review_chain(packet)


def test_packet_relation_tampering_fails_closed(tmp_path: Path) -> None:
    case = TamperCase(
        "packet-relation",
        "typed-relations.json",
        ("A_to_bridge", "source", "polarity"),
        "supported",
        "resolution.relation.polarity.unsupported",
    )
    packet = _tampered_review(tmp_path, case)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_review_chain(packet)


def test_packet_manifest_tampering_fails_closed(tmp_path: Path) -> None:
    case = TamperCase(
        "packet-manifest",
        "packet-manifest.json",
        ("packet_digest",),
        "0" * 64,
        "resolution.manifest.packet_digest.match",
    )
    packet = _tampered_review(tmp_path, case)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_review_chain(packet)


@pytest.mark.parametrize("review_name", ["review-summary.json", "review-seal.json"])
def test_packet_manifest_rejects_circular_review_inclusion(
    tmp_path: Path, review_name: str
) -> None:
    packet = tmp_path / review_name
    shutil.copytree(PACKET_ROOT, packet)
    manifest_path = packet / "packet-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_sha256"][review_name] = hashlib.sha256(
        (packet / review_name).read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AssertionError, match="^resolution.manifest.graph.closed$"):
        validate_review_chain(packet)


@pytest.mark.parametrize("artifact", ["review-summary.json", "review-seal.json"])
def test_review_schema_rejects_unexpected_fields(tmp_path: Path, artifact: str) -> None:
    case = TamperCase(
        f"extra-{artifact}",
        artifact,
        ("unexpected",),
        True,
        (
            "review.summary.fields.exact"
            if artifact == "review-summary.json"
            else "review.seal.fields.exact"
        ),
    )
    packet = _tampered_review(tmp_path, case)
    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_review_chain(packet)
