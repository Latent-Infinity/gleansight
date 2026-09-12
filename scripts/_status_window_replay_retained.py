from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nsqd.domain.status_window_replay import (
    EXPECTED_CORPUS_VERSION,
    EXPECTED_EXTRACTED_RECORDS_DIGEST,
    EXPECTED_HARVESTED_AT,
    EXPECTED_RECORD_COUNT,
    EXPECTED_SNAPSHOT_ID,
    build_status_window_replay_summary,
    validate_status_window_replay_artifact,
)
from nsqd.domain.trusted_files import sha256_file_digest

if TYPE_CHECKING:
    from scripts import _status_window_replay_io as _io
elif __package__:
    from . import _status_window_replay_io as _io
else:
    import _status_window_replay_io as _io


def load_retained_records(
    *, output_dir: Path, approved_rows: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows_path = output_dir / _io.ROWS_NAME
    artifact_path = output_dir / _io.ARTIFACT_NAME
    summary_path = output_dir / _io.SUMMARY_NAME
    rows_payload = _io._load_json(rows_path)
    artifact = validate_status_window_replay_artifact(_io._load_json(artifact_path))
    summary = _io._load_json(summary_path)
    rows_sha256 = sha256_file_digest(rows_path, max_bytes=_io.MAX_PACKET_FILE_BYTES)
    artifact_sha256 = sha256_file_digest(artifact_path, max_bytes=_io.MAX_PACKET_FILE_BYTES)
    if summary != build_status_window_replay_summary(
        artifact,
        rows_sha256=rows_sha256,
        artifact_sha256=artifact_sha256,
    ):
        raise _io.ReplayValidationError(
            "retained replay summary does not bind the retained packet bytes"
        )
    records = artifact["extracted_records"]
    if rows_payload != {
        "schema_version": 1,
        "snapshot_id": EXPECTED_SNAPSHOT_ID,
        "corpus_version": EXPECTED_CORPUS_VERSION,
        "record_count": EXPECTED_RECORD_COUNT,
        "harvested_at_utc": EXPECTED_HARVESTED_AT,
        "records": records,
    }:
        raise _io.ReplayValidationError(
            "retained rows must match the digest, count, UTC, membership, snapshot_id, "
            "and corpus_version bindings"
        )
    if artifact["extracted_records_digest"] != EXPECTED_EXTRACTED_RECORDS_DIGEST:
        raise _io.ReplayValidationError(
            "retained rows digest does not match the independent sealed digest"
        )
    for record in records:
        approved = approved_rows.get(str(record["record_id"]))
        expected = {
            "record_id": str(record["record_id"]),
            "source_paper_id": str(approved["source_paper_id"]) if approved else "",
            "domain_policy_id": str(approved["domain_policy_id"]) if approved else "",
            "type": str(approved["type"]) if approved else "",
            "harvested_at": EXPECTED_HARVESTED_AT,
        }
        if approved and "coordinates" in approved:
            expected["coordinates"] = approved["coordinates"]
        if approved is None or record != expected:
            raise _io.ReplayValidationError(
                "retained snapshot member must bind to an approved projection row"
            )
    return records
