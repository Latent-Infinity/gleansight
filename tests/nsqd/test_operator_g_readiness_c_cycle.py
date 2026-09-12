from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from nsqd.domain.operator_g_census import StructuredValue

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = (
    REPO_ROOT / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle-correction"
)
PREDECESSOR_ROOT = REPO_ROOT / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle"
PREDECESSOR_MANIFEST = "../nsqd-operator-g-readiness-census-2026-09-09-c-cycle/packet-manifest.json"
PREDECESSOR_DIGEST = "d984bab7ad819fdfd45031d840900b9f0bb74241ae319f5473fe4bb5d3272bad"
C_CYCLE_MANIFEST = (
    "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-09/packet-manifest.json"
)
C_CYCLE_MANIFEST_SHA256 = "baf5ab583e294c4eebee2fcaa2cc73c5e4a985cfd74005af7cf21a39e4aa0abf"
C_CYCLE_PACKET_DIGEST = "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90"


def _mapping(value: StructuredValue) -> dict[str, StructuredValue]:
    assert isinstance(value, dict)
    return value


def _json(path: Path) -> dict[str, StructuredValue]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")))


def test_c_cycle_successor_preserves_sealed_zero_census() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")

    census = _mapping(packet["census"])
    assert census["status"] == "complete"
    assert census["scope_file_count"] == 292
    assert census["scope_snapshot_digest"] == (
        "b915babcefdab9d7403ccf0ec2444bbae505f06d4315a8d78f8a746703049334"
    )
    assert packet["external_trust_inputs"] == {
        "trusted_approval_count": 0,
        "trusted_evidence_artifact_count": 0,
    }
    assert packet["qualifying_approved_record_count"] == 0
    assert packet["qualifying_record_digests"] == []
    assert packet["records"] == []


def test_c_cycle_successor_is_report_only_and_has_no_authority() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")

    assert packet["authorization_state"] == "report_only"
    assert packet["runtime_authorized"] is False
    assert packet["resurrection_authorized"] is False
    assert packet["operator_g_eligible"] is False
    assert packet["evidence_sufficient"] is False
    authority = _mapping(packet["authority"])
    assert authority == {
        "packet_inclusion_authorized": False,
        "operator_g_eligibility_implied": False,
        "restart_authorized": False,
        "resurrection_authorized": False,
        "runtime_authorized": False,
    }


def test_c_cycle_successor_chains_to_validated_protocol_packet() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    predecessor = _mapping(packet["predecessor"])
    predecessor_manifest = _json(PREDECESSOR_ROOT / "packet-manifest.json")

    assert predecessor == {
        "manifest": PREDECESSOR_MANIFEST,
        "packet_digest": PREDECESSOR_DIGEST,
    }
    assert predecessor_manifest["packet_digest"] == PREDECESSOR_DIGEST


def test_c_cycle_source_bindings_preserve_corrected_c_trigger() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    bindings = packet["source_bindings"]
    assert isinstance(bindings, list)
    observed_roles: dict[str, str] = {}
    for value in bindings:
        binding = _mapping(value)
        path = binding["path"]
        role = binding["role"]
        digest = binding["sha256"]
        assert isinstance(path, str)
        assert isinstance(role, str)
        assert isinstance(digest, str)
        observed_roles[path] = role
        assert len(digest) == 64

    assert observed_roles[C_CYCLE_MANIFEST] == "operator_c_cycle_trigger"
    assert hashlib.sha256((REPO_ROOT / C_CYCLE_MANIFEST).read_bytes()).hexdigest() == (
        C_CYCLE_MANIFEST_SHA256
    )
    assert _json(REPO_ROOT / C_CYCLE_MANIFEST)["packet_digest"] == C_CYCLE_PACKET_DIGEST


def test_c_cycle_manifest_replays_deterministically() -> None:
    manifest = _json(PACKET_ROOT / "packet-manifest.json")
    artifacts = _mapping(manifest["artifact_sha256"])
    readiness_digest = hashlib.sha256((PACKET_ROOT / "readiness.json").read_bytes()).hexdigest()
    packet_preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()

    assert manifest["schema_version"] == 1
    assert artifacts == {"readiness.json": readiness_digest}
    assert manifest["packet_digest"] == hashlib.sha256(packet_preimage).hexdigest()


def test_c_cycle_timestamp_is_exact_sealed_utc_packet_time() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    created_at = packet["created_at_utc"]
    assert isinstance(created_at, str)

    parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    assert created_at == "2026-09-10T00:34:17Z"
    assert parsed.tzinfo == UTC
