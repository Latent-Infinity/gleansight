from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

from nsqd.domain.operator_baselines import verify_scratch_execution_receipt
from nsqd.domain.project import canonical_reviewed_projection_digest, projection_record_id
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
from nsqd.domain.trusted_files import (
    load_verified_yaml_mapping,
    read_verified_repo_file,
    read_verified_repo_text,
    require_non_symlink_leaf,
    require_non_symlink_path,
    require_non_symlink_path_within_root,
    sha256_file_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKET_DIR = REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
OUTPUT_DIR = REPO_ROOT / "docs" / "reviews" / "nsqd-status-window-calendar-replay-2026-09-02"
ARTIFACT_NAME = "calendar-replay-artifact.json"
ROWS_NAME = "extracted-timestamp-rows.json"
SUMMARY_NAME = "review-summary.json"
README_NAME = "README.md"
MAX_PACKET_FILE_BYTES = 8 * 1024 * 1024
ALLOWED_TEMP_ROOTS = tuple(
    {
        Path(tempfile.gettempdir()).resolve(strict=False),
        Path(tempfile.gettempdir()),
        Path("/tmp").resolve(strict=False),
        Path("/tmp"),
    }
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_verified_baseline_evidence() -> dict[str, Any]:
    payload = json.loads(
        read_verified_repo_text(
            repo_root=REPO_ROOT,
            relative_path=Path(
                "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/baseline-evidence.json"
            ),
            expected_root=Path("docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01"),
            field="baseline_evidence_path",
            max_bytes=MAX_PACKET_FILE_BYTES,
        )
    )
    if not isinstance(payload, dict):
        raise ValueError("baseline_evidence_path must contain a JSON object")
    return payload


def _verify_historical_receipt() -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = _load_verified_baseline_evidence()
    runtime = verify_scratch_execution_receipt(
        baseline["execution_receipt"],
        scratch_runtime=baseline["scratch_runtime"],
    )
    return baseline, runtime


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = db_path.resolve(strict=False).as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _require_temp_output_path_without_descendant_symlinks(path: Path) -> None:
    absolute = path if path.is_absolute() else path.resolve(strict=False)
    current = Path(absolute.anchor) if absolute.anchor else Path(".")
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    allowed_alias_prefixes: set[Path] = set()
    for root in ALLOWED_TEMP_ROOTS:
        lexical = root if root.is_absolute() else root.resolve(strict=False)
        allowed_alias_prefixes.add(lexical)
        allowed_alias_prefixes.update(lexical.parents)
        resolved = lexical.resolve(strict=False)
        allowed_alias_prefixes.add(resolved)
        allowed_alias_prefixes.update(resolved.parents)
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink() and current not in allowed_alias_prefixes:
            raise ValueError("output_dir must not resolve through a symlink")


def _allowed_temp_output_dir(path: Path) -> Path | None:
    expanded = path.expanduser()
    resolved = expanded.resolve(strict=False)
    for root in ALLOWED_TEMP_ROOTS:
        root_resolved = root.resolve(strict=False)
        if expanded == root or root in expanded.parents:
            require_non_symlink_path_within_root(
                path=resolved, root=root_resolved, field="output_dir"
            )
            return resolved
        if resolved == root_resolved or root_resolved in resolved.parents:
            require_non_symlink_path_within_root(
                path=resolved, root=root_resolved, field="output_dir"
            )
            return resolved
    return None


def _require_output_dir(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_absolute() and ".." in candidate.parts:
        raise ValueError("output_dir must not contain parent traversal")
    if not candidate.is_absolute() and ".." in candidate.parts:
        raise ValueError("output_dir must not contain parent traversal")
    repo_candidate = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    if repo_candidate.resolve(strict=False) == OUTPUT_DIR.resolve(strict=False):
        require_non_symlink_path(repo_candidate, field="output_dir")
        require_non_symlink_path_within_root(
            path=repo_candidate,
            root=REPO_ROOT,
            field="output_dir",
        )
        require_non_symlink_leaf(path=repo_candidate, field="output_dir")
        if repo_candidate.exists() and not repo_candidate.is_dir():
            raise ValueError("output_dir must be a directory")
        return OUTPUT_DIR.resolve()
    temp_match = _allowed_temp_output_dir(candidate)
    if temp_match is not None:
        _require_temp_output_path_without_descendant_symlinks(candidate)
        require_non_symlink_leaf(path=temp_match, field="output_dir")
        if candidate.exists() and not candidate.is_dir():
            raise ValueError("output_dir must be a directory")
        return temp_match
    raise ValueError(
        "output_dir must stay inside the sealed output directory or an allowlisted system temp root"
    )


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
    resolved_output = _require_output_dir(output_dir)
    resolved_output.mkdir(parents=True, exist_ok=True)
    rows_path = resolved_output / ROWS_NAME
    artifact_path = resolved_output / ARTIFACT_NAME
    summary_path = resolved_output / SUMMARY_NAME
    readme_path = resolved_output / README_NAME

    rows_payload = {
        "schema_version": 1,
        "snapshot_id": EXPECTED_SNAPSHOT_ID,
        "corpus_version": EXPECTED_CORPUS_VERSION,
        "record_count": len(records),
        "harvested_at_utc": EXPECTED_HARVESTED_AT,
        "records": records,
    }
    rows_path.write_text(
        json.dumps(rows_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = build_status_window_replay_summary(
        artifact,
        rows_sha256=sha256_file_digest(rows_path, max_bytes=MAX_PACKET_FILE_BYTES),
        artifact_sha256=sha256_file_digest(artifact_path, max_bytes=MAX_PACKET_FILE_BYTES),
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readme_path.write_text(_readme_text(), encoding="utf-8")


def _readme_text() -> str:
    return "\n".join(
        [
            "# Status-window calendar replay",
            "",
            "**State:** report-only research artifact; runtime unauthorized",
            "",
            "This directory seals a portable replay comparing the current inclusive",
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
            "`sealed_at_utc` records the original packet sealing time, not the",
            "source harvest time, current-as-of replay time, or derived future",
            "sensitivity time.",
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
            "- `review-summary.json` — file digests and verification notes for human",
            "  review.",
            "",
            "## Verify",
            "",
            "```bash",
            "uv run pytest " + "\\",
            "  tests/nsqd/test_operator_activation_packets.py " + "\\",
            "  tests/nsqd/test_operator_c.py " + "\\",
            "  tests/nsqd/test_operator_c_evidence_packet.py " + "\\",
            "  tests/nsqd/test_operator_e.py " + "\\",
            "  tests/nsqd/test_operator_e_cooccurrence.py " + "\\",
            "  tests/nsqd/test_operator_e_report_only_candidates.py " + "\\",
            "  tests/nsqd/test_operator_e_broader_prior_art.py " + "\\",
            "  tests/nsqd/test_operator_baselines.py " + "\\",
            "  tests/nsqd/test_status_window_ablation.py " + "\\",
            "  tests/nsqd/test_status_window_receipt_replay.py " + "\\",
            "  tests/nsqd/test_map.py " + "\\",
            "  tests/nsqd/test_cli.py " + "\\",
            "  tests/nsqd/test_operator_a.py " + "\\",
            "  tests/nsqd/test_operator_b.py -q --no-cov",
            "uv run python scripts/replay_status_window_ablation.py " + "\\",
            "  --verify-current-receipt",
            "uv run python scripts/replay_status_window_ablation.py " + "\\",
            "  --output-dir docs/reviews/nsqd-status-window-calendar-replay-2026-09-02",
            "```",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--verify-current-receipt", action="store_true")
    args = parser.parse_args()

    baseline, _runtime = _verify_historical_receipt()
    if args.verify_current_receipt:
        print(
            json.dumps(
                {"verified_current_receipt": True, "snapshot_id": EXPECTED_SNAPSHOT_ID},
                sort_keys=True,
            )
        )
        return 0
    db_path = Path(str(baseline["scratch_runtime"]["db_path"]))
    records = _extract_records(db_path)
    artifact = _build_artifact(
        records, sqlite_sha256=str(baseline["execution_receipt"]["sqlite_sha256"])
    )
    _write_outputs(args.output_dir, records=records, artifact=artifact)
    print(
        json.dumps(
            {
                "artifact_path": str(_require_output_dir(args.output_dir) / ARTIFACT_NAME),
                "record_count": len(records),
                "snapshot_id": EXPECTED_SNAPSHOT_ID,
                "verified_current_receipt": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
