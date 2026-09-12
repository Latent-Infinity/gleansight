from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = REPO_ROOT / "docs"
PACKET_ROOT = DOCS_ROOT / "reviews" / "nsqd-operator-activation-2026-08-30"
FOLLOWUP_ROOT = DOCS_ROOT / "reviews" / "nsqd-operator-c-evidence-2026-09-08"
RESOLUTION_ROOT = DOCS_ROOT / "reviews" / "nsqd-operator-c-evidence-resolution-2026-09-09"


def _load_operator_c() -> dict[str, Any]:
    payload = yaml.safe_load((PACKET_ROOT / "operator-c.yaml").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_operator_c_independently_reviewed_pointers_bind_current_resolution() -> None:
    packet = _load_operator_c()

    reviewed_pointers = {
        "latest_independently_reviewed_evidence_report": (
            "../nsqd-operator-c-evidence-resolution-2026-09-09/review-summary.json"
        ),
        "latest_independently_reviewed_evidence_review_seal": (
            "../nsqd-operator-c-evidence-resolution-2026-09-09/review-seal.json"
        ),
        "latest_independently_reviewed_evidence_packet_manifest": (
            "../nsqd-operator-c-evidence-resolution-2026-09-09/packet-manifest.json"
        ),
    }
    for field, path in reviewed_pointers.items():
        assert packet[field] == path
    assert packet["latest_evidence_report"] == (
        "../nsqd-operator-c-evidence-resolution-2026-09-09/review-summary.json"
    )
    assert packet["latest_evidence_review_seal"] == (
        "../nsqd-operator-c-evidence-resolution-2026-09-09/review-seal.json"
    )
    assert packet["latest_independently_reviewed_evidence_packet_digest"] == (
        "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90"
    )
    for field, name in (
        ("latest_evidence_review_summary_sha256", "review-summary.json"),
        ("latest_evidence_review_seal_sha256", "review-seal.json"),
    ):
        assert packet[field] == hashlib.sha256((RESOLUTION_ROOT / name).read_bytes()).hexdigest()
    assert packet["latest_independently_reviewed_evidence_packet_manifest_sha256"] == (
        hashlib.sha256((RESOLUTION_ROOT / "packet-manifest.json").read_bytes()).hexdigest()
    )
    reviewed_cycle = next(
        cycle
        for cycle in packet["evidence_cycles"]
        if cycle["cycle_id"] == "operator-c-evidence-2026-09-08"
    )
    assert reviewed_cycle == {
        "cycle_id": "operator-c-evidence-2026-09-08",
        "decision": "insufficient_evidence",
        "packet_digest": "7dc279651b4e70c2838d80b7e00cf7e9da7102ad93dcb87c462103f1c6cd4f43",
        "post_review_remediation_status": "independently_confirmed",
        "review_status": "needs_fix",
        "substantive_evidence_verdict": "confirmed",
    }


def test_operator_c_current_resolution_pointer_and_results_are_exact() -> None:
    packet = _load_operator_c()

    assert packet["known_limitations"][5] == (
        "the current packet received a confirmed bounded negative report-only Todo 6 technical "
        "review; this is not human acceptance or positive bridge evidence"
    )
    assert packet["required_check_results"]["independent_review"] == (
        "confirmed_bounded_negative_report_only_conclusion"
    )
    assert packet["latest_executed_at_utc"] == "2026-09-09T20:27:38Z"
    assert packet["latest_evidence_packet_manifest"] == (
        "../nsqd-operator-c-evidence-resolution-2026-09-09/packet-manifest.json"
    )
    assert packet["latest_evidence_packet_digest"] == (
        "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90"
    )
    assert packet["latest_evidence_packet_manifest_sha256"] == (
        "baf5ab583e294c4eebee2fcaa2cc73c5e4a985cfd74005af7cf21a39e4aa0abf"
    )
    assert packet["latest_evidence_artifact_sha256"] == {
        "README.md": "213382cf673e63049d941bbf3e37b461a6bad48ff91c25f595ed91df6993bd36",
        "acquisition-receipts.json": (
            "082168d9014904b3eee00c4fa0358a9f100acf8a029dabb9fc910b6bb38ea213"
        ),
        "bibliographic-query-receipts.json": (
            "b0be5323ddd7b46939320ce2efe488785742d090c0722e0626716d390e2e67a8"
        ),
        "evidence-ledger.json": (
            "fc70c082fb821a5eaf21d6ec56acaa83194536f6bd64311ceb19355d7cd1a71c"
        ),
        "source-extracts.jsonl": (
            "d9c92f4257fd41cc32bb204c765254125288088d8c08b19e828e4aae1fa355d4"
        ),
        "typed-relations.json": (
            "f737e4747d2bc18deb2cb4c5fd4150ca8797e5f1a6092356d8d6c44ca4ceff0c"
        ),
    }
    assert packet["latest_cycle_results"] == {
        "accepted_bridge": False,
        "bibliographic_response_bytes_retained": False,
        "bibliographic_response_replay": "unavailable_after_temporary_file_cleanup",
        "bibliographic_response_retention": "not_retained_repository_policy",
        "candidate_output_count": 0,
        "evidence_sufficient": False,
        "full_text_inspected": True,
        "human_acceptance": "not_requested",
        "independent_review": "confirmed_negative_conclusion",
        "offline_integrity_verification": {
            "acquisition_receipt_metadata": "available",
            "packet_manifest": "available",
            "source_extract_records": "available",
            "typed_relation_records": "available",
        },
        "offline_quote_containment_replay": "unavailable_after_temporary_file_cleanup",
        "openalex_interactions": "not_observed_within_bounded_queries",
        "operator_c_status": "blocked",
        "operator_d_status": "blocked",
        "retrieval_basis": "official_versioned_arxiv_pdfs",
        "retrieval_method": "curl_http",
        "runtime_activation": "not_authorized",
        "semantic_scholar_interactions": "unavailable_from_service_http_429",
        "source_bytes_retained": False,
        "source_bytes_retention": "not_retained_repository_policy",
        "universal_noninteraction": "unverified",
        "universal_noninteraction_claimed": False,
    }
    assert packet["evidence_cycles"][-1] == {
        "cycle_id": "operator-c-evidence-resolution-2026-09-09",
        "decision": "insufficient_evidence",
        "human_acceptance": "not_requested",
        "packet_digest": "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90",
        "review_scope": "bounded_negative_report_only_evidence_conclusion",
        "review_status": "confirmed_negative_conclusion",
        "reviewer_session_id": "ses_f76edce6dffe6gPRxa2M13UADd",
        "technical_review_is_human_acceptance": False,
    }


def test_current_operator_authority_binds_packet_pointers_and_hashes() -> None:
    packet = _load_operator_c()
    manifest_path = PACKET_ROOT / packet["latest_evidence_packet_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == (packet["latest_evidence_packet_manifest_sha256"])
    )
    assert manifest["packet_digest"] == packet["latest_evidence_packet_digest"]
    assert manifest["artifact_sha256"] == packet["latest_evidence_artifact_sha256"]
    for name, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((RESOLUTION_ROOT / name).read_bytes()).hexdigest() == digest


def test_current_resolution_packet_binds_its_detached_negative_review() -> None:
    packet = _load_operator_c()
    current_digest = packet["latest_evidence_packet_digest"]
    reviewed_digest = packet["latest_independently_reviewed_evidence_packet_digest"]
    review_summary = json.loads((RESOLUTION_ROOT / "review-summary.json").read_text())
    review_seal = json.loads((RESOLUTION_ROOT / "review-seal.json").read_text())

    assert current_digest == reviewed_digest
    assert review_summary["packet_digest"] == reviewed_digest
    assert review_seal["packet_digest"] == reviewed_digest
    assert review_summary["authority"]["technical_review_is_human_acceptance"] is False
    assert review_summary["authority"]["human_acceptance"] == "not_requested"
    assert review_summary["authority"]["todo_7_advancement_authorized"] is False
