from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nsqd.domain.operator_g_types import StructuredValue

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
REVIEWS_ROOT: Final = REPO_ROOT / "docs" / "reviews"
REVIEWED_AT: Final = "2026-09-12T02:17:15Z"
REVIEWER: Final[dict[str, StructuredValue]] = {
    "identity": "Oracle / independent technical reviewer",
    "session_id": "ses_f6ca7a5d6ffemcwDdH9apgEn0i",
    "model": "openai/gpt-5.6-sol",
    "executor_session_id": "ses_f6cb4cc04ffeOyvmPb4oyg0YzC",
    "reviewer_differs_from_executor": True,
}
LIMITATIONS: Final[list[StructuredValue]] = [
    "Inherited staging time is not independently provable.",
    "The historical SQLite source is unavailable.",
    "Copied Operator C external source bytes were not independently reacquired.",
    "The F-PROP-001 human_approved field remains historical_claim_unverified.",
    "This technical review is not human acceptance and grants no evidence approval, schema "
    "admission, or runtime authority.",
]
AUTHORITY: Final[dict[str, StructuredValue]] = {
    "technical_review_is_human_acceptance": False,
    "human_acceptance_authorized": False,
    "evidence_approval_authorized": False,
    "schema_admission_authorized": False,
    "runtime_authorized": False,
}


@dataclass(frozen=True, slots=True)
class ReviewedPacket:
    directory: str
    scope: str
    manifest_sha256: str
    packet_digest: str


PACKETS: Final = (
    ReviewedPacket(
        "nsqd-operator-f-readiness-2026-09-12-implementation-binding",
        "operator_f_implementation_binding",
        "7aefc06baace0604ca994eecaae04c1508aae9487ff64d1aa1fbfcef446fc245",
        "e82490162af6f8da4507aef5cfe019869a2caecdaa3cf985a0751e794c8d62fe",
    ),
    ReviewedPacket(
        "nsqd-operator-activation-2026-09-12-pointer-sync",
        "operator_activation_pointer_sync",
        "10614b26f2fa4edc9e2954f16ecfafad45cbc18e1566af94f6ff3ef5dbb743ea",
        "c767f3ced5be85ddd1aa8432106e207e6b0c262593a90a69a910a4518444ebed",
    ),
)


def _json(path: Path) -> dict[str, StructuredValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_oracle_reviews_bind_exact_successor_packets_without_authority() -> None:
    for packet in PACKETS:
        root = REVIEWS_ROOT / packet.directory
        summary_path = root / "technical-review-summary.json"
        summary = _json(summary_path)
        seal = _json(root / "technical-review-seal.json")

        assert _sha256(root / "packet-manifest.json") == packet.manifest_sha256
        assert summary == {
            "schema_version": 1,
            "verdict": "PASS",
            "seal_ready": True,
            "reviewed_at_utc": REVIEWED_AT,
            "reviewer": REVIEWER,
            "review_scope": packet.scope,
            "reviewed_packet": {
                "manifest_sha256": packet.manifest_sha256,
                "packet_digest": packet.packet_digest,
            },
            "findings": [],
            "limitations": LIMITATIONS,
            "authority": AUTHORITY,
        }
        assert seal == {
            "schema_version": 1,
            "verdict": "PASS",
            "technical_review_summary_sha256": _sha256(summary_path),
            "packet_manifest_sha256": packet.manifest_sha256,
            "packet_digest": packet.packet_digest,
            "reviewed_at_utc": REVIEWED_AT,
            "reviewer": REVIEWER,
            "review_scope": packet.scope,
            "limitations": LIMITATIONS,
            "authority": AUTHORITY,
        }


def test_oracle_review_artifacts_are_detached_from_reviewed_manifests() -> None:
    for packet in PACKETS:
        manifest = _json(REVIEWS_ROOT / packet.directory / "packet-manifest.json")
        artifacts = manifest["artifact_sha256"]

        assert isinstance(artifacts, dict)
        assert "technical-review-summary.json" not in artifacts
        assert "technical-review-seal.json" not in artifacts
