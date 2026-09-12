from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Final

import pytest

from tests.nsqd.operator_c_evidence_cycle_3_support import (
    MalformedPacketCase,
    tamper_packet,
)
from tests.nsqd.operator_c_followup_support import (
    validate_followup_manifest,
    validate_followup_packet,
    validate_followup_semantics,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PACKET_ROOT: Final = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-2026-09-08"
CORE_ARTIFACT_NAMES: Final = {
    "README.md",
    "acquisition-receipts.json",
    "bibliographic-query-receipts.json",
    "evidence-ledger.json",
    "packet-manifest.json",
    "source-extracts.jsonl",
}
ARTIFACT_NAMES: Final = CORE_ARTIFACT_NAMES | {"review-seal.json", "review-summary.json"}
PACKET_DIGEST: Final = "7dc279651b4e70c2838d80b7e00cf7e9da7102ad93dcb87c462103f1c6cd4f43"
type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

SEMANTIC_TAMPER_CASES: Final = (
    (
        MalformedPacketCase(
            "receipt_byte_count_type",
            "acquisition-receipts.json",
            ("records", 0, "byte_count"),
            "2342053",
        ),
        "followup.receipt.byte_count.positive_integer",
    ),
    (
        MalformedPacketCase(
            "dangling_extract_receipt_reference",
            "source-extracts.jsonl",
            (0, "receipt_id"),
            "missing-receipt",
        ),
        "followup.extract.receipt_id.known",
    ),
    (
        MalformedPacketCase(
            "bibliographic_http_status",
            "bibliographic-query-receipts.json",
            ("records", 0, "http_status"),
            403,
        ),
        "followup.bibliographic.http_status.ok",
    ),
    (
        MalformedPacketCase(
            "runtime_authority_ledger_field",
            "evidence-ledger.json",
            ("runtime_authorized",),
            True,
        ),
        "followup.ledger.runtime_authorized.false",
    ),
)


def _json(path: Path) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _mappings(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_mapping(item) for item in value]


def _string(value: JsonValue) -> str:
    assert isinstance(value, str) and value.strip()
    return value


def _tampered_packet(tmp_path: Path, case: MalformedPacketCase) -> Path:
    packet = tmp_path / "packet"
    shutil.copytree(PACKET_ROOT, packet)
    tamper_packet(packet, case)
    return packet


def _whitespace_mutated_packet(tmp_path: Path) -> Path:
    packet = tmp_path / "packet"
    shutil.copytree(PACKET_ROOT, packet)
    ledger_path = packet / "evidence-ledger.json"
    ledger_path.write_text(ledger_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    return packet


def test_followup_packet_records_openreview_note_version_and_pdf_receipt_metadata() -> None:
    receipts = _json(PACKET_ROOT / "acquisition-receipts.json")
    by_id = {_string(row["receipt_id"]): row for row in _mappings(receipts["records"])}
    pdf = by_id["OpenReview:BZfkxSasd3v2#pdf"]
    note = by_id["OpenReview:BZfkxSasd3v2#api2-note"]

    assert pdf["note_id"] == "BZfkxSasd3"
    assert pdf["note_version"] == 2
    assert pdf["magic_hex"] == "25504446"
    assert pdf["observed_media_type"] == "application/pdf"
    assert pdf["byte_count"] == 2342053
    assert pdf["sha256"] == "afa32af2b8ae2609ee34dbfb94690b3d63273676530107fabc8a12cfce8eab86"
    assert pdf["final_url"] == "https://openreview.net/pdf?id=BZfkxSasd3"
    assert note["exposed_pdf_locator"] == "/pdf/6ddc0f748a4cbe51806b18a848fcf17e6b28f3ee.pdf"


def test_followup_packet_closes_extract_query_digest_and_authority_references() -> None:
    validate_followup_packet(PACKET_ROOT)
    extracts = [
        _json_line
        for line in (PACKET_ROOT / "source-extracts.jsonl").read_text(encoding="utf-8").splitlines()
        if isinstance((_json_line := json.loads(line)), dict)
    ]

    assert {_string(row["source_id"]) for row in extracts} == {
        "OpenReview:BZfkxSasd3v2",
        "arXiv:1402.2198v1",
        "arXiv:2602.04643v2",
        "doi:10.2139/ssrn.6855118",
    }
    assert {_string(row["evidence_scope"]) for row in extracts} >= {
        "method",
        "result",
        "limitation",
        "reference",
    }
    assert {path.name for path in PACKET_ROOT.iterdir()} == ARTIFACT_NAMES


def test_followup_detached_review_chain_binds_independent_bounded_verdict() -> None:
    summary_path = PACKET_ROOT / "review-summary.json"
    summary = _json(summary_path)
    review = _mapping(summary["independent_review"])
    remediation = _mapping(summary["post_review_remediation"])
    authority = _mapping(summary["authority"])
    seal = _json(PACKET_ROOT / "review-seal.json")

    assert summary["schema_version"] == 1
    assert summary["packet_digest"] == PACKET_DIGEST
    assert review == {
        "approval_scope": "bounded_negative_report_only_evidence_conclusion",
        "original_limitations": [
            "The cycle-3 detached seal binds only the 2026-09-07 packet.",
            (
                "The 2026-09-08 follow-up has a packet manifest but no detached "
                "independent-review seal."
            ),
            "This read-only verdict was not appended to the ledger.",
            (
                "Only a representative 6-of-11 live query subset was reissued; all 11 "
                "stored receipts were structurally inspected."
            ),
        ],
        "original_blocking_reasons": [
            "Todo 5 was checked before independent verification.",
            (
                "The executor's DoneClaim embedded its own confirmed AdversarialVerify "
                "instead of awaiting a separate reviewer."
            ),
            (
                "The task-time agent-browser process remains alive as PID 54380 despite "
                "the cleanup claim that agent-browser was closed."
            ),
        ],
        "original_verdict": "needs-fix",
        "reviewed_at_utc": "2026-09-08T07:18:34.416Z",
        "reviewer_model": "openai/gpt-5.6-sol",
        "reviewer_session_id": "ses_f802fe0bcffel0U98vSq8ZrALK",
        "substantive_evidence_verdict": "confirmed",
    }
    assert remediation == {
        "cleanup_event": "task-5-browser-residue-cleanup",
        "cleanup_status": "independently_confirmed",
        "historical_review_verdict_preserved": True,
        "pid": 54380,
        "postcheck": {
            "agent_browser_absent": True,
            "cdp_9242_listener_absent": True,
            "cloakbrowser_absent": True,
            "openreview_pdf_absent": True,
            "playwright_mcp_untouched": True,
            "todo_5_temp_files_absent": True,
        },
        "remediation_scope": "post_review_browser_cleanup_only",
        "substantive_review_retroactively_altered": False,
        "termination": "SIGTERM",
        "termination_exit": 0,
    }
    assert authority == {
        "accepted_bridge": False,
        "authorization_state": "report_only",
        "candidate_combinations": [],
        "candidate_outputs": [],
        "evidence_sufficient": False,
        "human_acceptance": "not_requested",
        "operator_c_status": "blocked",
        "operator_d_status": "blocked",
        "runtime_authorized": False,
    }
    assert seal == {
        "approval_scope": "bounded_negative_report_only_evidence_conclusion",
        "authorization_state": "report_only",
        "human_acceptance": "not_requested",
        "original_review_verdict": "needs-fix",
        "packet_digest": PACKET_DIGEST,
        "review_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "reviewer_model": "openai/gpt-5.6-sol",
        "reviewer_session_id": "ses_f802fe0bcffel0U98vSq8ZrALK",
        "runtime_authorized": False,
        "schema_version": 1,
        "substantive_evidence_verdict": "confirmed",
    }


@pytest.mark.parametrize(
    ("case", "guard"), SEMANTIC_TAMPER_CASES, ids=[case.name for case, _ in SEMANTIC_TAMPER_CASES]
)
def test_followup_semantics_reject_named_tamper_at_its_guard(
    tmp_path: Path, case: MalformedPacketCase, guard: str
) -> None:
    packet = _tampered_packet(tmp_path, case)

    with pytest.raises(AssertionError, match=f"^{re.escape(guard)}$"):
        validate_followup_semantics(packet)


@pytest.mark.parametrize(
    "case", [case for case, _ in SEMANTIC_TAMPER_CASES], ids=lambda case: case.name
)
def test_followup_manifest_rejects_each_semantic_tamper(
    tmp_path: Path, case: MalformedPacketCase
) -> None:
    packet = _tampered_packet(tmp_path, case)

    guard = f"followup.manifest.artifact_sha256.match:{case.artifact}"
    with pytest.raises(AssertionError, match=f"^{re.escape(guard)}$"):
        validate_followup_manifest(packet)


def test_followup_manifest_rejects_semantically_neutral_json_whitespace(tmp_path: Path) -> None:
    packet = _whitespace_mutated_packet(tmp_path)

    validate_followup_semantics(packet)
    guard = "followup.manifest.artifact_sha256.match:evidence-ledger.json"
    with pytest.raises(AssertionError, match=f"^{re.escape(guard)}$"):
        validate_followup_manifest(packet)


def test_followup_composed_validator_runs_manifest_after_semantics(tmp_path: Path) -> None:
    packet = _whitespace_mutated_packet(tmp_path)

    guard = "followup.manifest.artifact_sha256.match:evidence-ledger.json"
    with pytest.raises(AssertionError, match=f"^{re.escape(guard)}$"):
        validate_followup_packet(packet)
