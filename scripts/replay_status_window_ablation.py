from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nsqd.domain.project import canonical_reviewed_projection_digest, projection_record_id
from nsqd.domain.status_window_replay import (
    EXPECTED_CORPUS_VERSION,
    EXPECTED_HARVESTED_AT,
    EXPECTED_RECORD_COUNT,
    EXPECTED_SNAPSHOT_ID,
    EXPECTED_SQLITE_SHA256,
)
from nsqd.domain.trusted_files import (
    load_verified_yaml_mapping,
    read_verified_repo_file,
    read_verified_repo_text,
)

if TYPE_CHECKING:
    from scripts import _status_window_replay_io as _io
    from scripts import _status_window_replay_packet as _packet
    from scripts import _status_window_replay_retained as _retained
elif __name__ == "__main__" and not __package__:
    import _status_window_replay_io as _io
    import _status_window_replay_packet as _packet
    import _status_window_replay_retained as _retained
else:
    from scripts import _status_window_replay_io as _io
    from scripts import _status_window_replay_packet as _packet
    from scripts import _status_window_replay_retained as _retained

REPO_ROOT = _io.REPO_ROOT
MAX_PACKET_FILE_BYTES = _io.MAX_PACKET_FILE_BYTES
OUTPUT_DIR = _io.OUTPUT_DIR
RETAINED_SOURCE_DIR = _io.RETAINED_SOURCE_DIR
ARTIFACT_NAME = _io.ARTIFACT_NAME
_connect_read_only = _io._connect_read_only
_require_output_dir = _io._require_output_dir
_verify_historical_receipt = _io._verify_historical_receipt
_build_artifact = _packet._build_artifact
_write_outputs = _packet._write_outputs
_readme_text = _packet._readme_text


def _approved_projection_rows() -> dict[str, dict[str, Any]]:
    import yaml

    rows: dict[str, dict[str, Any]] = {}
    manifest_specs = (
        (
            REPO_ROOT
            / "docs"
            / "reviews"
            / "nsqd-projection-review-2026-08-28"
            / "final"
            / "manifest.toml",
            Path("docs/reviews/nsqd-projection-review-2026-08-28/final"),
        ),
        (
            REPO_ROOT / "tests" / "fixtures" / "approved" / "nsqd" / "manifest.toml",
            Path("tests/fixtures/approved/nsqd"),
        ),
    )
    for manifest_path, root in manifest_specs:
        manifest = tomllib.loads(
            read_verified_repo_text(
                repo_root=REPO_ROOT,
                relative_path=manifest_path.relative_to(REPO_ROOT),
                expected_root=root,
                field="manifest_path",
                max_bytes=MAX_PACKET_FILE_BYTES,
            )
        )
        fixture = manifest.get("fixture")
        if not isinstance(fixture, dict):
            raise ValueError("approved projection manifest fixture table is required")
        for item in fixture.values():
            if not isinstance(item, dict) or item.get("kind") != "corpus-paper-paraphrase":
                continue
            manifest_row = {str(key): value for key, value in item.items()}
            projection_rel = root / str(manifest_row["path"])
            payload = load_verified_yaml_mapping(
                repo_root=REPO_ROOT,
                relative_path=projection_rel,
                expected_root=root,
                field="projection_path",
                max_bytes=MAX_PACKET_FILE_BYTES,
            )
            projection_bytes = read_verified_repo_file(
                repo_root=REPO_ROOT,
                relative_path=projection_rel,
                expected_root=root,
                field="projection_path",
                max_bytes=MAX_PACKET_FILE_BYTES,
            )
            parsed = yaml.safe_load(projection_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("projection_path must load a YAML mapping")
            if str(manifest_row.get("id") or "") != str(payload.get("id") or ""):
                raise ValueError("manifest row id does not match projection id")
            if str(manifest_row.get("domain_policy_id") or "") != str(
                payload.get("domain_policy_id") or ""
            ):
                raise ValueError("manifest row domain_policy_id does not match projection")
            if str(manifest_row.get("source_paper_id") or "") != str(
                payload.get("source_paper_id") or ""
            ):
                raise ValueError("manifest row source_paper_id does not match projection")
            if str(manifest_row.get("review_status") or "") != "approved":
                raise ValueError("manifest row review_status must be approved")
            if not str(manifest_row.get("reviewer") or "").strip():
                raise ValueError("manifest row reviewer is required")
            if not str(manifest_row.get("approved_at") or "").strip():
                raise ValueError("manifest row approved_at is required")
            content_sha256 = hashlib.sha256(projection_bytes).hexdigest()
            if str(manifest_row.get("content_sha256") or "") != content_sha256:
                raise ValueError("manifest row content_sha256 does not match projection bytes")
            reviewed_digest = canonical_reviewed_projection_digest(parsed)
            manifest_reviewed_projection = manifest_row.get("reviewed_projection_sha256")
            if (
                manifest_reviewed_projection is not None
                and str(manifest_reviewed_projection) != reviewed_digest
            ):
                raise ValueError(
                    "manifest row reviewed_projection_sha256 does not match projection contract"
                )
            coords = payload.get("coordinates")
            if not isinstance(coords, dict):
                coords = payload.get("research_descriptor")
            projected_record_id = projection_record_id(parsed)
            if projected_record_id in rows:
                raise ValueError("duplicate projected_record_id in approved projection rows")
            row: dict[str, Any] = {
                "manifest_id": str(manifest_row["id"]),
                "projected_record_id": projected_record_id,
                "source_paper_id": str(payload["source_paper_id"]),
                "domain_policy_id": str(payload["domain_policy_id"]),
                "type": str(payload.get("type") or "paper"),
                "reviewed_projection_digest": reviewed_digest,
            }
            if isinstance(coords, dict) and coords:
                row["coordinates"] = coords
            rows[projected_record_id] = row
    return rows


def _extract_records(db_path: Path) -> list[dict[str, Any]]:
    approved_rows = _approved_projection_rows()
    connection = _connect_read_only(db_path)
    try:
        snapshot = connection.execute(
            (
                "SELECT corpus_version, record_ids_json "
                "FROM nsqd_corpus_snapshots WHERE snapshot_id = ?"
            ),
            (EXPECTED_SNAPSHOT_ID,),
        ).fetchone()
        if snapshot is None:
            raise ValueError(
                "approved snapshot is missing from the verified historical scratch sqlite"
            )
        corpus_version = int(snapshot["corpus_version"])
        if corpus_version != EXPECTED_CORPUS_VERSION:
            raise ValueError("approved snapshot corpus_version is invalid")
        record_ids = json.loads(str(snapshot["record_ids_json"]))
        if not isinstance(record_ids, list) or len(record_ids) != EXPECTED_RECORD_COUNT:
            raise ValueError("approved snapshot must contain exactly 11 record ids")
        records: list[dict[str, Any]] = []
        for record_id in record_ids:
            row = connection.execute(
                "SELECT payload_json FROM nsqd_corpus_records WHERE record_id = ?",
                (str(record_id),),
            ).fetchone()
            if row is None:
                raise ValueError("snapshot member is missing from nsqd_corpus_records")
            payload = json.loads(str(row["payload_json"]))
            if str(payload.get("record_id")) != str(record_id):
                raise ValueError(
                    "snapshot member payload record_id does not match snapshot membership"
                )
            harvested_at = str(payload.get("harvested_at") or "")
            if harvested_at != EXPECTED_HARVESTED_AT:
                raise ValueError(
                    "snapshot member harvested_at must match the observed "
                    "receipt-bound UTC timestamp"
                )
            approved = approved_rows.get(str(record_id))
            if approved is None:
                raise ValueError(
                    "snapshot member must bind to an approved projection row for status replay"
                )
            if str(approved["projected_record_id"]) != str(record_id):
                raise ValueError(
                    "snapshot member projection_record_id does not match "
                    "approved projection identity"
                )
            if str(approved["source_paper_id"]) != str(payload["source_paper_id"]):
                raise ValueError(
                    "snapshot member source_paper_id does not match approved projection identity"
                )
            if str(approved["domain_policy_id"]) != str(payload["domain_policy_id"]):
                raise ValueError(
                    "snapshot member domain_policy_id does not match approved projection identity"
                )
            extracted: dict[str, Any] = {
                "record_id": str(payload["record_id"]),
                "source_paper_id": str(approved["source_paper_id"]),
                "domain_policy_id": str(approved["domain_policy_id"]),
                "type": str(approved["type"]),
                "harvested_at": harvested_at,
            }
            if "coordinates" in approved:
                extracted["coordinates"] = approved["coordinates"]
            records.append(extracted)
    finally:
        connection.close()
    if len(records) != EXPECTED_RECORD_COUNT:
        raise ValueError("receipt-bound extraction returned the wrong record count")
    return records


def _load_retained_records() -> list[dict[str, Any]]:
    return _retained.load_retained_records(
        output_dir=RETAINED_SOURCE_DIR,
        approved_rows=_approved_projection_rows(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    verification = parser.add_mutually_exclusive_group()
    verification.add_argument("--verify-current-receipt", action="store_true")
    verification.add_argument("--verify-retained-replay", action="store_true")
    args = parser.parse_args()

    if args.verify_current_receipt:
        _verify_historical_receipt()
        receipt_result = {"snapshot_id": EXPECTED_SNAPSHOT_ID, "verified_current_receipt": True}
        print(json.dumps(receipt_result, sort_keys=True))
        return 0
    records = _load_retained_records()
    result = {
        "record_count": len(records),
        "snapshot_id": EXPECTED_SNAPSHOT_ID,
        "verified_current_receipt": False,
        "verified_retained_replay": True,
    }
    if args.verify_retained_replay:
        print(json.dumps(result, sort_keys=True))
        return 0
    artifact = _build_artifact(records, sqlite_sha256=EXPECTED_SQLITE_SHA256)
    _write_outputs(args.output_dir, records=records, artifact=artifact)
    result["artifact_path"] = str(_require_output_dir(args.output_dir) / ARTIFACT_NAME)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
