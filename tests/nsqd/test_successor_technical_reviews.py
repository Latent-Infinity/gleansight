from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Final

import pytest

from tests.nsqd.successor_technical_review_support import (
    AUTHORITY,
    EXECUTOR_SESSION,
    LIMITATIONS,
    REVIEWED_AT,
    REVIEWER_IDENTITY,
    REVIEWER_SESSION,
    SEAL_NAME,
    SUCCESSORS,
    SUMMARY_NAME,
    JsonMapping,
    JsonValue,
    Successor,
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
    SummaryTamper("missing-reviewer-session", ("reviewer", "session_id"), None),
    SummaryTamper("mismatched-reviewer-session", ("reviewer", "session_id"), "ses_wrong"),
    SummaryTamper("mismatched-reviewer-model", ("reviewer", "model"), "openai/wrong-model"),
    SummaryTamper("executor-session-collision", ("reviewer", "session_id"), EXECUTOR_SESSION),
    SummaryTamper(
        "transferred-predecessor-identity",
        ("reviewer", "identity"),
        "oracle / independent-evidence-reviewer",
    ),
    SummaryTamper(
        "transferred-predecessor-time",
        ("reviewed_at_utc",),
        "2026-09-10T02:28:53Z",
    ),
    SummaryTamper("altered-limitations", ("limitations",), ["limitations removed"]),
    SummaryTamper(
        "false-human-acceptance",
        ("authority", "technical_review_is_human_acceptance"),
        True,
    ),
    SummaryTamper("human-acceptance-invented", ("authority", "human_acceptance"), "accepted"),
    SummaryTamper(
        "evidence-authority",
        ("authority", "evidence_approval_authorized"),
        True,
    ),
    SummaryTamper(
        "schema-authority",
        ("authority", "schema_admission_authorized"),
        True,
    ),
    SummaryTamper(
        "operational-authority",
        ("authority", "operational_authority_granted"),
        True,
    ),
    SummaryTamper("runtime-authority", ("authority", "runtime_authorized"), True),
    SummaryTamper(
        "final-g-census-authority",
        ("authority", "final_g_census_authorized"),
        True,
    ),
)


def _set_mapping_value(payload: JsonMapping, path: tuple[str, ...], value: JsonValue) -> None:
    target = payload
    for part in path[:-1]:
        target = mapping(target[part])
    target[path[-1]] = value


@pytest.mark.parametrize("successor", SUCCESSORS, ids=lambda item: item.label)
def test_detached_technical_review_chain_replays_for_successor(successor: Successor) -> None:
    summary_sha256 = validate_chain(successor)

    assert len(summary_sha256) == 64
    assert (successor.root / SUMMARY_NAME).is_file()
    assert (successor.root / SEAL_NAME).is_file()


@pytest.mark.parametrize("successor", SUCCESSORS, ids=lambda item: item.label)
def test_packet_manifest_excludes_detached_technical_reviews(successor: Successor) -> None:
    manifest = json_mapping(successor.root / "packet-manifest.json")
    artifacts = mapping(manifest["artifact_sha256"])

    assert SUMMARY_NAME not in artifacts
    assert SEAL_NAME not in artifacts


@pytest.mark.parametrize("case", SUMMARY_TAMPERS, ids=lambda item: item.name)
def test_summary_semantic_tampering_fails_closed(case: SummaryTamper) -> None:
    summary = copy.deepcopy(json_mapping(SUCCESSORS[0].root / SUMMARY_NAME))
    _set_mapping_value(summary, case.path, case.replacement)

    with pytest.raises(AssertionError):
        validate_summary(summary)


@pytest.mark.parametrize("case", SUMMARY_TAMPERS, ids=lambda item: item.name)
def test_seal_semantic_tampering_fails_closed(case: SummaryTamper) -> None:
    successor = SUCCESSORS[0]
    seal = copy.deepcopy(json_mapping(successor.root / SEAL_NAME))
    _set_mapping_value(seal, case.path, case.replacement)

    with pytest.raises(AssertionError):
        validate_seal(seal, successor, sha256(successor.root / SUMMARY_NAME))


@pytest.mark.parametrize("successor", SUCCESSORS, ids=lambda item: item.label)
@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("technical_review_summary_sha256", "0" * 64),
        ("packet_manifest_sha256", "0" * 64),
        ("packet_digest", "0" * 64),
        ("reviewed_at_utc", "2026-09-10T02:28:53Z"),
        ("review_scope", "predecessor_scope"),
    ),
)
def test_seal_binding_tampering_fails_closed(
    successor: Successor,
    field: str,
    replacement: JsonValue,
) -> None:
    seal = copy.deepcopy(json_mapping(successor.root / SEAL_NAME))
    seal[field] = replacement

    with pytest.raises(AssertionError):
        validate_seal(seal, successor, sha256(successor.root / SUMMARY_NAME))


def test_exact_pass_identity_time_limitations_and_non_authority_are_preserved() -> None:
    summary = json_mapping(SUCCESSORS[0].root / SUMMARY_NAME)
    reviewer = mapping(summary["reviewer"])
    authority = mapping(summary["authority"])

    assert reviewer["identity"] == REVIEWER_IDENTITY
    assert reviewer["session_id"] == REVIEWER_SESSION
    assert reviewer["session_id"] != reviewer["executor_session_id"]
    assert summary["reviewed_at_utc"] == REVIEWED_AT
    assert summary["limitations"] == LIMITATIONS
    assert authority == AUTHORITY
    assert authority["human_acceptance"] == "not_requested"
    assert all(value is False for value in authority.values() if isinstance(value, bool))


@pytest.mark.parametrize("name", (SUMMARY_NAME, SEAL_NAME))
def test_status_predecessor_review_summary_is_not_repurposed(name: str) -> None:
    status = SUCCESSORS[2]

    assert name != "review-summary.json"
    assert (status.root / "review-summary.json").is_file()
