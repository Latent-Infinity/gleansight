from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from nsqd.domain.operator_g_census import StructuredValue

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = REPO_ROOT / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review"
PREDECESSOR_ROOT = (
    REPO_ROOT / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle-correction"
)
PREDECESSOR_MANIFEST = (
    "../nsqd-operator-g-readiness-census-2026-09-09-c-cycle-correction/packet-manifest.json"
)
PREDECESSOR_DIGEST = "18808bc2186244f432fd7742dfbaba18c11d1eefcd0e7d90e31b972a501e5844"
C_ROOT = "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-09"
C_MANIFEST_SHA256 = "baf5ab583e294c4eebee2fcaa2cc73c5e4a985cfd74005af7cf21a39e4aa0abf"
C_PACKET_DIGEST = "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90"
REVIEW_SUMMARY_SHA256 = "643fc415cc2f6b266a7a8bf4c04fdf11e34ede3947dd3be090ad241d3a5f04d4"
REVIEW_SEAL_SHA256 = "43119d95b784fa587ae640815b8b71f6c96ccbc6f12d72ab1875edaff39971f2"
REVIEWER_SESSION = "ses_f76edce6dffe6gPRxa2M13UADd"
SUCCESSOR_DIGEST = "3a9070604f9e622bc3d2d56f666cc762ae31d85d7bad85c06e531e056c1efc87"


def _mapping(value: StructuredValue) -> dict[str, StructuredValue]:
    assert isinstance(value, dict)
    return value


def _json(path: Path) -> dict[str, StructuredValue]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")))


def test_operator_c_authority_binds_confirmed_negative_review_separately() -> None:
    packet = yaml.safe_load(
        (REPO_ROOT / "docs/reviews/nsqd-operator-activation-2026-08-30/operator-c.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert packet["latest_evidence_packet_digest"] == C_PACKET_DIGEST
    assert packet["latest_evidence_review_summary_sha256"] == REVIEW_SUMMARY_SHA256
    assert packet["latest_evidence_review_seal_sha256"] == REVIEW_SEAL_SHA256
    assert packet["latest_independently_reviewed_evidence_report"] == (
        "../nsqd-operator-c-evidence-resolution-2026-09-09/review-summary.json"
    )
    assert packet["latest_independently_reviewed_evidence_review_seal"] == (
        "../nsqd-operator-c-evidence-resolution-2026-09-09/review-seal.json"
    )
    assert packet["latest_independently_reviewed_evidence_packet_digest"] == C_PACKET_DIGEST
    assert packet["latest_technical_review"] == {
        "reviewer_session_id": REVIEWER_SESSION,
        "verdict": "confirmed",
        "approval_scope": "bounded_negative_report_only_evidence_conclusion",
        "technical_review": "confirmed_negative_conclusion",
        "technical_review_is_human_acceptance": False,
        "human_acceptance": "not_requested",
        "accepted_bridge": False,
        "evidence_sufficient": False,
        "todo_7_advancement_authorized": False,
        "schema_admission_authorized": False,
        "runtime_authorized": False,
    }


def test_rejected_c_review_successor_preserves_sealed_zero_authority_census() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")

    census = _mapping(packet["census"])
    assert census["status"] == "complete"
    assert census["scope_file_count"] == 294
    assert census["scope_snapshot_digest"] == (
        "dea63f0476427e930a9b97460045cfa333db2fe78a62c7fd5014332af01097ad"
    )
    assert packet["external_trust_inputs"] == {
        "trusted_approval_count": 0,
        "trusted_evidence_artifact_count": 0,
    }
    assert packet["qualifying_approved_record_count"] == 0
    assert packet["qualifying_record_digests"] == []
    assert packet["records"] == []
    assert packet["authority"] == {
        "packet_inclusion_authorized": False,
        "operator_g_eligibility_implied": False,
        "restart_authorized": False,
        "resurrection_authorized": False,
        "runtime_authorized": False,
    }


def test_rejected_c_review_successor_preserves_chain_and_detached_review_bindings() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    predecessor = _json(PREDECESSOR_ROOT / "packet-manifest.json")
    source_bindings = packet["source_bindings"]
    assert isinstance(source_bindings, list)
    bindings = {value["path"]: value for value in source_bindings if isinstance(value, dict)}

    assert packet["predecessor"] == {
        "manifest": PREDECESSOR_MANIFEST,
        "packet_digest": PREDECESSOR_DIGEST,
    }
    assert predecessor["packet_digest"] == PREDECESSOR_DIGEST
    assert bindings[f"{C_ROOT}/packet-manifest.json"]["sha256"] == C_MANIFEST_SHA256
    assert bindings[f"{C_ROOT}/review-summary.json"]["sha256"] == REVIEW_SUMMARY_SHA256
    assert bindings[f"{C_ROOT}/review-seal.json"]["sha256"] == REVIEW_SEAL_SHA256


def test_c_review_successor_manifest_replays() -> None:
    manifest = _json(PACKET_ROOT / "packet-manifest.json")
    readiness_digest = hashlib.sha256((PACKET_ROOT / "readiness.json").read_bytes()).hexdigest()
    artifacts = {"readiness.json": readiness_digest}
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()

    assert manifest == {
        "artifact_sha256": artifacts,
        "packet_digest": hashlib.sha256(preimage).hexdigest(),
        "schema_version": 1,
    }
    assert manifest["packet_digest"] == SUCCESSOR_DIGEST
