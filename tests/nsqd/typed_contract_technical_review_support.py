from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonMapping = dict[str, JsonValue]

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
REVIEW_ROOT: Final = (
    REPO_ROOT
    / "docs"
    / "reviews"
    / "nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup"
)
SUMMARY_NAME: Final = "technical-review-summary.json"
SEAL_NAME: Final = "technical-review-seal.json"
REVIEWED_AT: Final = "2026-09-11T21:20:05Z"
REVIEWER_SESSION: Final = "ses_f6dafb5a0ffeMkTHiek00vUS3v"
STALE_REVIEWER_SESSION: Final = "ses_f819dc40fffetJEezNrkJgf7rK"
EXECUTOR_SESSION: Final = "ses_f6dc1450cffe8xl6Hk0usAakxS"
MANIFEST_SHA256: Final = "c265f11a5e3f3ab170fb54d66cd2f5ddc945689be1d503763a2610ff54c279a3"
PACKET_DIGEST: Final = "5ac872a5b5267c2e64d4171039ef9af6d00556723c38cb4916bd61b9f76d4675"

REVIEWER: Final[JsonMapping] = {
    "identity": "Sisyphus-Junior / independent-typed-contract-reviewer",
    "session_id": REVIEWER_SESSION,
    "model": "openai/gpt-5.6-sol",
    "executor_session_id": EXECUTOR_SESSION,
    "reviewer_differs_from_executor": True,
    "superseded_reviewer_session_id": STALE_REVIEWER_SESSION,
    "superseded_reviewer_session_rejected": True,
}
SCOPE: Final[JsonMapping] = {
    "members": 319,
    "source_bindings": 34,
    "trust_counts": [0, 0, 0],
}
HASHES: Final[JsonMapping] = {
    "scope_snapshot_digest": "f593a38f25ccd79284d81401f79e311873fc83ed9a82e5bc728330ab85d1ef5e",
    "readiness_sha256": "448e568ab1556319250db5b4e80c2973fb22e24422eee55937ca3d3b5550890f",
    "packet_manifest_sha256": MANIFEST_SHA256,
    "packet_digest": PACKET_DIGEST,
    "predecessor_digest": "2dc39d073f845dc208d4747959b954b473b60a9d48ebe5050d1287b0a16a0d6e",
}
LIMITATIONS: Final[list[JsonValue]] = [
    "Historical scratch SQLite bytes are unavailable; current-receipt verification failed "
    "closed, while retained replay passed with 11 records.",
    "Copied external C sources were not reacquired because network access was prohibited.",
    "This is technical verification only. It grants no human acceptance, evidence approval, "
    "packet inclusion, eligibility, restart, resurrection, or runtime authority.",
]
AUTHORITY: Final[JsonMapping] = {
    "human_acceptance": "not_requested",
    "evidence_approval_authorized": False,
    "packet_inclusion_authorized": False,
    "operator_g_eligibility_authorized": False,
    "restart_authorized": False,
    "resurrection_authorized": False,
    "runtime_authorized": False,
}


def json_mapping(path: Path) -> JsonMapping:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"typed_contract_review.mapping:{path.name}"
    return payload


def mapping(value: JsonValue) -> JsonMapping:
    assert isinstance(value, dict), "typed_contract_review.value.mapping"
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(payload: JsonMapping) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def validate_summary(summary: JsonMapping) -> None:
    assert summary == {
        "schema_version": 1,
        "verdict": "PASS",
        "seal_ready": True,
        "reviewed_at_utc": REVIEWED_AT,
        "reviewer": REVIEWER,
        "scope": SCOPE,
        "hashes": HASHES,
        "findings": [],
        "limitations": LIMITATIONS,
        "technical_review_is_human_acceptance": False,
        "authority": AUTHORITY,
    }, "typed_contract_review.summary.exact"


def validate_seal(seal: JsonMapping, summary_sha256: str) -> None:
    assert seal == {
        "schema_version": 1,
        "verdict": "PASS",
        "technical_review_summary_sha256": summary_sha256,
        "packet_manifest_sha256": MANIFEST_SHA256,
        "packet_digest": PACKET_DIGEST,
        "reviewed_at_utc": REVIEWED_AT,
        "reviewer": REVIEWER,
    }, "typed_contract_review.seal.exact"


def validate_chain(root: Path = REVIEW_ROOT) -> str:
    manifest = json_mapping(root / "packet-manifest.json")
    artifacts = mapping(manifest["artifact_sha256"])
    assert SUMMARY_NAME not in artifacts and SEAL_NAME not in artifacts, (
        "typed_contract_review.manifest.detached"
    )
    assert sha256(root / "packet-manifest.json") == MANIFEST_SHA256
    assert manifest["packet_digest"] == PACKET_DIGEST
    summary_path = root / SUMMARY_NAME
    summary = json_mapping(summary_path)
    validate_summary(summary)
    assert summary_path.read_bytes() == canonical_bytes(summary)
    summary_sha256 = sha256(summary_path)
    seal_path = root / SEAL_NAME
    seal = json_mapping(seal_path)
    validate_seal(seal, summary_sha256)
    assert seal_path.read_bytes() == canonical_bytes(seal)
    return summary_sha256
