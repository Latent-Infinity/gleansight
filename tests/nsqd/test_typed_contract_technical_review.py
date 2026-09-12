from __future__ import annotations

import copy
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from tests.nsqd.typed_contract_technical_review_support import (
    AUTHORITY,
    EXECUTOR_SESSION,
    HASHES,
    LIMITATIONS,
    MANIFEST_SHA256,
    PACKET_DIGEST,
    REVIEW_ROOT,
    REVIEWED_AT,
    REVIEWER_SESSION,
    SEAL_NAME,
    STALE_REVIEWER_SESSION,
    SUMMARY_NAME,
    JsonMapping,
    JsonValue,
    canonical_bytes,
    json_mapping,
    mapping,
    sha256,
    validate_chain,
    validate_seal,
    validate_summary,
)


@dataclass(frozen=True, slots=True)
class SummaryTamper:
    name: str
    path: tuple[str, ...]
    replacement: JsonValue


SUMMARY_TAMPERS: Final = (
    SummaryTamper("reviewer-session", ("reviewer", "session_id"), STALE_REVIEWER_SESSION),
    SummaryTamper("executor-separation", ("reviewer", "executor_session_id"), REVIEWER_SESSION),
    SummaryTamper("reviewed-at", ("reviewed_at_utc",), "2026-09-11T21:20:06Z"),
    SummaryTamper("readiness-sha", ("hashes", "readiness_sha256"), "0" * 64),
    SummaryTamper("packet-digest", ("hashes", "packet_digest"), "0" * 64),
    SummaryTamper("predecessor-digest", ("hashes", "predecessor_digest"), "0" * 64),
    SummaryTamper("scope-members", ("scope", "members"), 318),
    SummaryTamper("source-bindings", ("scope", "source_bindings"), 33),
    SummaryTamper("trust-counts", ("scope", "trust_counts"), [1, 0, 0]),
    SummaryTamper("limitation-deletion", ("limitations",), LIMITATIONS[:-1]),
    SummaryTamper("human-acceptance", ("technical_review_is_human_acceptance",), True),
    SummaryTamper("human-acceptance-state", ("authority", "human_acceptance"), "accepted"),
    SummaryTamper("evidence-authority", ("authority", "evidence_approval_authorized"), True),
    SummaryTamper("packet-authority", ("authority", "packet_inclusion_authorized"), True),
    SummaryTamper("runtime-authority", ("authority", "runtime_authorized"), True),
)


def _set_mapping_value(payload: JsonMapping, path: tuple[str, ...], value: JsonValue) -> None:
    target = payload
    for part in path[:-1]:
        target = mapping(target[part])
    target[path[-1]] = value


@pytest.mark.parametrize("missing_name", (SUMMARY_NAME, SEAL_NAME))
def test_detached_review_fails_closed_when_artifact_is_absent(
    tmp_path: Path,
    missing_name: str,
) -> None:
    packet = tmp_path / "packet"
    shutil.copytree(REVIEW_ROOT, packet)
    (packet / missing_name).unlink()

    with pytest.raises(FileNotFoundError):
        validate_chain(packet)


@pytest.mark.parametrize("case", SUMMARY_TAMPERS, ids=lambda item: item.name)
def test_summary_semantic_tampering_fails_closed(case: SummaryTamper) -> None:
    summary = copy.deepcopy(json_mapping(REVIEW_ROOT / SUMMARY_NAME))
    _set_mapping_value(summary, case.path, case.replacement)

    with pytest.raises(AssertionError):
        validate_summary(summary)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("technical_review_summary_sha256", "0" * 64),
        ("packet_manifest_sha256", "0" * 64),
        ("packet_digest", "0" * 64),
        ("reviewed_at_utc", "2026-09-11T21:20:06Z"),
        ("reviewer", {}),
    ),
)
def test_seal_binding_tampering_fails_closed(field: str, replacement: JsonValue) -> None:
    seal = copy.deepcopy(json_mapping(REVIEW_ROOT / SEAL_NAME))
    seal[field] = replacement

    with pytest.raises(AssertionError):
        validate_seal(seal, sha256(REVIEW_ROOT / SUMMARY_NAME))


def test_corrected_independent_pass_chain_replays_exactly() -> None:
    summary_sha256 = validate_chain()
    summary = json_mapping(REVIEW_ROOT / SUMMARY_NAME)
    reviewer = mapping(summary["reviewer"])

    assert len(summary_sha256) == 64
    assert reviewer["session_id"] == REVIEWER_SESSION
    assert reviewer["session_id"] != EXECUTOR_SESSION
    assert reviewer["superseded_reviewer_session_id"] == STALE_REVIEWER_SESSION
    assert reviewer["superseded_reviewer_session_rejected"] is True
    assert summary["reviewed_at_utc"] == REVIEWED_AT
    assert summary["hashes"] == HASHES
    assert summary["limitations"] == LIMITATIONS
    assert summary["authority"] == AUTHORITY


def test_review_files_are_self_excluded_without_changing_census_or_packet() -> None:
    manifest = json_mapping(REVIEW_ROOT / "packet-manifest.json")
    artifacts = mapping(manifest["artifact_sha256"])
    summary = json_mapping(REVIEW_ROOT / SUMMARY_NAME)

    assert set(artifacts) == {"readiness.json"}
    assert SUMMARY_NAME not in artifacts
    assert SEAL_NAME not in artifacts
    assert sha256(REVIEW_ROOT / "packet-manifest.json") == MANIFEST_SHA256
    assert manifest["packet_digest"] == PACKET_DIGEST
    assert mapping(summary["hashes"])["scope_snapshot_digest"] == (
        "f593a38f25ccd79284d81401f79e311873fc83ed9a82e5bc728330ab85d1ef5e"
    )


def test_detached_artifacts_use_deterministic_canonical_json() -> None:
    for name in (SUMMARY_NAME, SEAL_NAME):
        payload = json_mapping(REVIEW_ROOT / name)
        assert (REVIEW_ROOT / name).read_bytes() == canonical_bytes(payload)
