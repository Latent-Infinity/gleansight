from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nsqd.domain.status_window_replay import (
    BOUNDARY_SENSITIVITY_SCENARIO_NOTE,
    CURRENT_AS_OF_SCENARIO_NOTE,
    EXPECTED_CORPUS_VERSION,
    EXPECTED_HARVESTED_AT,
    EXPECTED_RECORD_COUNT,
    EXPECTED_SNAPSHOT_ID,
    PROVENANCE_CAVEAT,
    SEALED_AT_UTC,
    STATUS_WINDOW_REPLAY_PACKET_KIND,
    build_status_window_replay_summary,
    compare_status_window_semantics,
    derive_boundary_sensitivity_as_of,
    extracted_records_digest,
    status_window_replay_artifact_digest,
    validate_status_window_replay_artifact,
)

if TYPE_CHECKING:
    from scripts import _status_window_replay_io as _io
elif __package__:
    from . import _status_window_replay_io as _io
else:
    import _status_window_replay_io as _io


def _build_artifact(records: list[dict[str, Any]], *, sqlite_sha256: str) -> dict[str, Any]:
    current_as_of = datetime.fromisoformat(EXPECTED_HARVESTED_AT)
    boundary_as_of = derive_boundary_sensitivity_as_of(records)
    report = {
        "schema_version": 1,
        "packet_kind": STATUS_WINDOW_REPLAY_PACKET_KIND,
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": True,
        "evidence_sufficient_scope": "human_decision_only",
        "runtime_status_window_days": 730,
        "sealed_at_utc": SEALED_AT_UTC,
        "harvested_at_provenance_caveat": PROVENANCE_CAVEAT,
        "extracted_records_digest": extracted_records_digest(records),
        "source_receipt": {
            "snapshot_id": EXPECTED_SNAPSHOT_ID,
            "corpus_version": EXPECTED_CORPUS_VERSION,
            "record_count": EXPECTED_RECORD_COUNT,
            "sqlite_sha256": sqlite_sha256,
            "harvested_at_utc": EXPECTED_HARVESTED_AT,
            "receipt_verified_exact": True,
        },
        "extracted_records": records,
        "scenarios": [
            {
                "scenario_id": "current_as_of",
                "scenario_kind": "observed_current_as_of",
                "as_of_utc": current_as_of.isoformat(),
                "scenario_note": CURRENT_AS_OF_SCENARIO_NOTE,
                "policy_results": {
                    policy_id: compare_status_window_semantics(
                        records,
                        domain_policy_id=policy_id,
                        as_of=current_as_of,
                        snapshot_state="production_valid",
                    )
                    for policy_id in ("finance/1", "optimization/1")
                },
            },
            {
                "scenario_id": "boundary_sensitivity",
                "scenario_kind": "boundary_sensitivity",
                "as_of_utc": boundary_as_of.isoformat(),
                "scenario_note": BOUNDARY_SENSITIVITY_SCENARIO_NOTE,
                "policy_results": {
                    policy_id: compare_status_window_semantics(
                        records,
                        domain_policy_id=policy_id,
                        as_of=boundary_as_of,
                        snapshot_state="production_valid",
                    )
                    for policy_id in ("finance/1", "optimization/1")
                },
            },
        ],
    }
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    validate_status_window_replay_artifact(report)
    return report


def _write_outputs(
    output_dir: Path, *, records: list[dict[str, Any]], artifact: dict[str, Any]
) -> None:
    resolved_output = _io._require_output_dir(output_dir)
    rows_payload = {
        "schema_version": 1,
        "snapshot_id": EXPECTED_SNAPSHOT_ID,
        "corpus_version": EXPECTED_CORPUS_VERSION,
        "record_count": len(records),
        "harvested_at_utc": EXPECTED_HARVESTED_AT,
        "records": records,
    }
    rows_bytes = (json.dumps(rows_payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    artifact_bytes = (json.dumps(artifact, indent=2, sort_keys=True) + "\n").encode("utf-8")
    summary = build_status_window_replay_summary(
        artifact,
        rows_sha256=hashlib.sha256(rows_bytes).hexdigest(),
        artifact_sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    summary_bytes = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")
    packet_bytes = {
        _io.REPORT_NAME: _report_text().encode("utf-8"),
        _io.ARTIFACT_NAME: artifact_bytes,
        _io.ROWS_NAME: rows_bytes,
        _io.SUMMARY_NAME: summary_bytes,
    }
    metadata = {
        "schema_version": 1,
        "workflow": "status-window-replay",
        "run_id": resolved_output.name,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "modeled_historical_timestamp_utc": EXPECTED_HARVESTED_AT,
        "artifact_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in packet_bytes.items()
        },
    }
    packet_bytes[_io.RUN_METADATA_NAME] = (
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with _io._open_output_dir_nofollow(resolved_output) as output_descriptor:
        _io._write_output_files(output_descriptor, packet_bytes)


def _report_text() -> str:
    return "\n".join(
        [
            "# Status-window calendar replay",
            "",
            "**Authorization:** report-only analysis; runtime unauthorized",
            "",
            "This run compares the current inclusive",
            "730-day status window against a 24-calendar-month UTC clamp replay over",
            "the approved snapshot",
            "`bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5`",
            "/ corpus version `11`.",
            "",
            "## Provenance boundary",
            "",
            "The timestamps here are real persisted values extracted from the",
            "receipt-bound historical scratch SQLite verified through",
            "`docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/baseline-evidence.json`.",
            "They are **not** proven original 2026-08-29 production-harvest",
            "timestamps because snapshot ids do not bind `harvested_at`.",
            "",
            "The artifact's `sealed_at_utc` records the historical model packet time, not the",
            "source harvest time, current-as-of replay time, or derived future",
            "sensitivity time. `run-metadata.json` separately records this run's actual UTC time.",
            "",
            "## Scenarios",
            "",
            "- `current_as_of`: observed report-as-of replay at",
            "  `2026-09-02T06:45:00+00:00`; explicit zero delta.",
            "- `boundary_sensitivity`: derived future sensitivity from the real",
            "  receipt-bound `harvested_at`; lifecycle semantics diverge while",
            "  cell-status outputs remain unchanged. This is sensitivity evidence,",
            "  not observed future production state.",
            "",
            "## Files",
            "",
            "- `extracted-timestamp-rows.json` — receipt-bound rows used by the",
            "  replay.",
            "- `calendar-replay-artifact.json` — portable self-validating replay",
            "  artifact with scenarios and canonical digest.",
            "- `review-summary.json` — domain artifact digests and verification notes for human",
            "  review.",
            "- `run-metadata.json` — actual run UTC and SHA-256 checksums for this bundle.",
            "",
        ]
    )
