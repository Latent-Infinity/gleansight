from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.composition import build_container, fixed_clock
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.domain.snapshot import sha256_hex
from nsqd.runner import run_job

MAX_PROJECT_FILE_BYTES = 256 * 1024
MAX_PROJECT_MANIFEST_BYTES = 256 * 1024


def run_project(
    *,
    projection_path: Path,
    manifest_path: Path,
    db_path: Path,
    index_path: Path,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    projection = load_verified_projection(
        projection_path=projection_path,
        manifest_path=manifest_path,
    )
    approved_digest = canonical_reviewed_projection_digest(projection)
    clock = fixed_clock(as_of) if as_of is not None else None
    container = build_container(
        db_path=db_path,
        index_path=index_path,
        clock=clock,
        approved_projection_digests=frozenset({approved_digest}),
    )
    return run_job(
        container,
        "project",
        {
            "domain_policy_id": str(projection.get("domain_policy_id") or ""),
            "projection": projection,
        },
        container.clock.now(),
    )


def load_verified_projection(
    *,
    projection_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    projection_bytes = _read_bounded_bytes(
        projection_path, MAX_PROJECT_FILE_BYTES, "projection fixture"
    )
    projection = _load_yaml_mapping(projection_bytes)
    manifest = _load_manifest(manifest_path)
    manifest_row = _find_manifest_row(
        manifest=manifest,
        manifest_path=manifest_path,
        projection_path=projection_path,
        projection=projection,
    )
    _verify_projection_fixture(
        projection_path=projection_path,
        projection=projection,
        manifest_row=manifest_row,
        fixture_bytes=projection_bytes,
    )
    return projection


def _load_yaml_mapping(content: bytes) -> dict[str, Any]:
    loaded = yaml.safe_load(content.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("projection fixture must be a mapping")
    return loaded


def _load_manifest(path: Path) -> dict[str, Any]:
    loaded = tomllib.loads(
        _read_bounded_text(path, MAX_PROJECT_MANIFEST_BYTES, "approved manifest")
    )
    if not isinstance(loaded, dict):
        raise ValueError("approved manifest must be a mapping")
    return loaded


def _read_bounded_text(path: Path, max_bytes: int, label: str) -> str:
    return _read_bounded_bytes(path, max_bytes, label).decode("utf-8")


def _read_bounded_bytes(path: Path, max_bytes: int, label: str) -> bytes:
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"{label} is too large")
    return content


def _find_manifest_row(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    projection_path: Path,
    projection: dict[str, Any],
) -> dict[str, Any]:
    fixture_table = manifest.get("fixture")
    if not isinstance(fixture_table, dict):
        raise ValueError("approved manifest fixture table is required")
    projection_id = _require_projection_string(projection, "id")
    projection_real_path = projection_path.resolve()
    matches: list[dict[str, Any]] = []
    for key, raw_row in fixture_table.items():
        if not isinstance(raw_row, dict):
            continue
        declared_path = raw_row.get("path")
        if not isinstance(declared_path, str) or not declared_path.strip():
            continue
        candidate_path = (manifest_path.parent / declared_path.strip()).resolve()
        if candidate_path != projection_real_path:
            continue
        row_id = raw_row.get("id")
        if not isinstance(row_id, str) or not row_id.strip():
            raise ValueError("approved manifest fixture id is required")
        if row_id.strip() != str(key):
            raise ValueError("approved manifest fixture key must match its declared id")
        matches.append(raw_row)
    if not matches:
        raise ValueError("projection fixture is not approved in manifest")
    if len(matches) != 1:
        raise ValueError("projection fixture path is ambiguous in manifest")
    match = matches[0]
    if _require_manifest_string(match, "id") != projection_id:
        raise ValueError("approved manifest id does not match projection fixture id")
    return match


def _verify_projection_fixture(
    *,
    projection_path: Path,
    projection: dict[str, Any],
    manifest_row: dict[str, Any],
    fixture_bytes: bytes,
) -> None:
    content_sha256 = sha256_hex(fixture_bytes)
    if content_sha256 != _require_manifest_string(manifest_row, "content_sha256"):
        raise ValueError("projection fixture content hash does not match manifest")
    _require_matching_field(manifest_row, projection, "kind")
    _require_matching_field(manifest_row, projection, "id")
    _require_matching_field(manifest_row, projection, "source_fixture_id")
    _require_matching_field(manifest_row, projection, "domain_policy_id")
    _require_matching_field(manifest_row, projection, "paper_id")
    _require_matching_field(manifest_row, projection, "source_paper_id")
    _require_matching_field(manifest_row, projection, "source_markdown_sha256")
    _require_matching_field(manifest_row, projection, "source_abstract_sha256")
    _require_matching_field(manifest_row, projection, "paraphrase_sha256")
    _require_matching_field(manifest_row, projection, "paraphrase_source")
    _require_matching_field(manifest_row, projection, "review_status")
    _require_cross_field_match(manifest_row, "reviewer", projection, "human_reviewer")
    _require_cross_field_match(manifest_row, "approved_at", projection, "human_approved_at")


def _require_matching_field(
    manifest_row: dict[str, Any], projection: dict[str, Any], field: str
) -> None:
    _require_cross_field_match(manifest_row, field, projection, field)


def _require_cross_field_match(
    manifest_row: dict[str, Any],
    manifest_field: str,
    projection: dict[str, Any],
    projection_field: str,
) -> None:
    manifest_value = _require_manifest_string(manifest_row, manifest_field)
    projection_value = _require_projection_string(projection, projection_field)
    if manifest_value != projection_value:
        raise ValueError(
            "projection fixture "
            f"{projection_field} does not match approved manifest {manifest_field}"
        )


def _require_manifest_string(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"approved manifest {field} is required")
    return value.strip()


def _require_projection_string(projection: dict[str, Any], field: str) -> str:
    value = projection.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"projection fixture {field} is required")
    return value.strip()
