from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Final

import pytest
from pydantic import ValidationError

from tests.nsqd.operator_evidence_resolution_protocol_support import validate_packet

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PACKET_ROOT: Final = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-evidence-resolution-2026-09-09"
REMEDIATION_FREEZE_UTC: Final = "2026-09-09T15:11:38Z"
PROTOCOL_SHA256: Final = "e1a800081299c89a39fda4f1f0cab08260e888add305d2609163051ad437f742"
PACKET_DIGEST: Final = "460986b339301e9012d56d34e5dca93bcfa30493d23b60317b9e992f9a5dc69c"
type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def _json(path: Path) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _temporary_packet(tmp_path: Path) -> Path:
    packet = tmp_path / "packet"
    shutil.copytree(PACKET_ROOT, packet)
    return packet


def _set_path(payload: dict[str, JsonValue], path: tuple[str, ...], value: JsonValue) -> None:
    target = payload
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value


def _rehash_manifest(packet: Path) -> None:
    protocol_digest = hashlib.sha256((packet / "protocol.json").read_bytes()).hexdigest()
    artifacts = {"protocol.json": protocol_digest}
    packet_digest = hashlib.sha256(
        json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = {"artifact_sha256": artifacts, "packet_digest": packet_digest, "schema_version": 1}
    (packet / "packet-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _tamper(tmp_path: Path, path: tuple[str, ...], value: JsonValue) -> Path:
    packet = _temporary_packet(tmp_path)
    payload = _json(packet / "protocol.json")
    _set_path(payload, path, value)
    (packet / "protocol.json").write_text(json.dumps(payload), encoding="utf-8")
    _rehash_manifest(packet)
    return packet


def test_canonical_operator_evidence_resolution_protocol_is_strict_and_non_authorizing() -> None:
    protocol = validate_packet(PACKET_ROOT)

    assert protocol.frozen_at_utc == protocol.cutoff_utc == REMEDIATION_FREEZE_UTC
    assert protocol.authority.validation_target_scope == "evaluation_only"
    states = protocol.authority.runtime_states
    assert {states.operator_c, states.operator_d, states.operator_f, states.operator_g} == {
        "disabled"
    }
    assert states.operator_e == "disabled_absent_explicit_override"
    assert protocol.operator_f.threshold_policy.numeric_thresholds == ()
    assert protocol.acquisition_outcomes_observed is False
    manifest = _json(PACKET_ROOT / "packet-manifest.json")
    assert manifest["artifact_sha256"] == {"protocol.json": PROTOCOL_SHA256}
    assert manifest["packet_digest"] == PACKET_DIGEST


@pytest.mark.parametrize(
    "path",
    [
        ("cutoff_utc",),
        ("source_identity", "identity_fields"),
        ("operator_f", "metrics"),
        ("operator_c", "negative_controls"),
        ("reviewer_independence", "reviewer_must_differ_from_producer"),
    ],
)
def test_protocol_rejects_missing_required_fields(tmp_path: Path, path: tuple[str, ...]) -> None:
    packet = _temporary_packet(tmp_path)
    payload = _json(packet / "protocol.json")
    target = payload
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target.pop(path[-1])
    (packet / "protocol.json").write_text(json.dumps(payload), encoding="utf-8")
    _rehash_manifest(packet)

    with pytest.raises(ValidationError):
        validate_packet(packet)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "1"),
        (("operator_c", "search_questions"), "not-a-list"),
        (("operator_f", "folds"), []),
    ],
)
def test_protocol_rejects_wrong_nested_types(
    tmp_path: Path, path: tuple[str, ...], value: JsonValue
) -> None:
    with pytest.raises(ValidationError):
        validate_packet(_tamper(tmp_path, path, value))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("cutoff_utc",), "2026-09-09T00:00:00+01:00"),
        (("discovery_envelope", "maximum_query_batches"), 4),
        (("operator_c", "query_budget", "maximum_candidates_per_batch"), 26),
        (("authority", "runtime_change_authorized"), True),
        (("operator_f", "threshold_policy", "outcomes_observed_at_approval"), True),
    ],
)
def test_protocol_rejects_boundary_or_authority_widening(
    tmp_path: Path, path: tuple[str, ...], value: JsonValue
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        validate_packet(_tamper(tmp_path, path, value))


def test_protocol_rejects_duplicate_source_identity_fields(tmp_path: Path) -> None:
    packet = _temporary_packet(tmp_path)
    payload = _json(packet / "protocol.json")
    identity = payload["source_identity"]
    assert isinstance(identity, dict)
    fields = identity["identity_fields"]
    assert isinstance(fields, list)
    fields.append(fields[0])
    (packet / "protocol.json").write_text(json.dumps(payload), encoding="utf-8")
    _rehash_manifest(packet)

    with pytest.raises(ValueError, match="unique"):
        validate_packet(packet)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("source_identity", "identity_fields"),
        ("operator_c", "negative_controls"),
        ("operator_f", "metrics"),
    ],
)
def test_protocol_rejects_missing_required_list_member(
    tmp_path: Path, section: str, field: str
) -> None:
    packet = _temporary_packet(tmp_path)
    payload = _json(packet / "protocol.json")
    nested = payload[section]
    assert isinstance(nested, dict)
    members = nested[field]
    assert isinstance(members, list)
    members.pop()
    (packet / "protocol.json").write_text(json.dumps(payload), encoding="utf-8")
    _rehash_manifest(packet)

    with pytest.raises(ValueError, match="incomplete"):
        validate_packet(packet)


def test_protocol_rejects_unknown_nested_field(tmp_path: Path) -> None:
    packet = _tamper(tmp_path, ("authority", "product_authority"), True)

    with pytest.raises(ValidationError):
        validate_packet(packet)


def test_protocol_rejects_manifest_tampering(tmp_path: Path) -> None:
    packet = _temporary_packet(tmp_path)
    manifest = _json(packet / "packet-manifest.json")
    manifest["packet_digest"] = "0" * 64
    (packet / "packet-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="packet digest mismatch"):
        validate_packet(packet)
