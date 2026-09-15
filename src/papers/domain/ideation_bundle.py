from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never

from nsqd.infrastructure.workflow_output import create_run_directory

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

IDEATION_ARTIFACTS: Final = (
    "evidence-map.json",
    "ideas.json",
    "critique.json",
    "provenance.json",
    "report.md",
)
PLAN_ARTIFACTS: Final = ("investigation-plan.json", "provenance.json", "report.md")


class BundleType(StrEnum):
    project_ideation = "project-ideation"
    selected_idea_plan = "selected-idea-plan"


@dataclass(frozen=True, slots=True)
class BundleIntegrityError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def write_json(path: Path, value: JsonValue) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_manifest(bundle: Path, names: tuple[str, ...]) -> dict[str, str]:
    hashes = {name: _sha256(bundle / name) for name in names}
    manifest: JsonValue = {name: digest for name, digest in hashes.items()}
    write_json(bundle / "manifest.json", manifest)
    return hashes


@contextmanager
def atomic_bundle(repo_root: Path, workflow: str) -> Iterator[tuple[Path, Path]]:
    published = create_run_directory(repo_root, workflow)
    staging = published.with_name(f".{published.name}.tmp")
    published.rename(staging)
    publication_complete = False
    try:
        yield staging, published
        staging.rename(published)
        publication_complete = True
    finally:
        if not publication_complete and staging.exists():
            shutil.rmtree(staging)


def verify_manifest(bundle: Path, bundle_type: BundleType) -> dict[str, str]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise BundleIntegrityError("bundle path is not a regular directory")
    try:
        raw = json.loads(read_verified_text(bundle / "manifest.json"))
    except (BundleIntegrityError, json.JSONDecodeError) as exc:
        raise BundleIntegrityError("bundle manifest is missing or invalid") from exc
    if not isinstance(raw, dict) or not all(
        isinstance(name, str) and isinstance(digest, str) for name, digest in raw.items()
    ):
        raise BundleIntegrityError("bundle manifest is invalid")
    hashes = {str(name): str(digest) for name, digest in raw.items()}
    expected_names = _expected_artifacts(bundle_type)
    if set(hashes) != set(expected_names):
        raise BundleIntegrityError("bundle manifest has an invalid artifact set")
    try:
        actual_names = {path.name for path in bundle.iterdir()}
    except OSError as exc:
        raise BundleIntegrityError("bundle artifact set cannot be read") from exc
    if actual_names != {*expected_names, "manifest.json"}:
        raise BundleIntegrityError("bundle directory has an invalid artifact set")
    if any(
        len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
        for digest in hashes.values()
    ):
        raise BundleIntegrityError("bundle manifest contains an invalid digest")
    for name, expected in hashes.items():
        path = bundle / name
        if hashlib.sha256(_read_regular_bytes(path)).hexdigest() != expected:
            raise BundleIntegrityError(f"bundle hash mismatch: {name}")
    return hashes


def read_verified_text(path: Path, expected_sha256: str | None = None) -> str:
    content = _read_regular_bytes(path)
    if expected_sha256 is not None and hashlib.sha256(content).hexdigest() != expected_sha256:
        raise BundleIntegrityError(f"bundle hash mismatch: {path.name}")
    try:
        return content.decode()
    except UnicodeDecodeError as exc:
        raise BundleIntegrityError(f"bundle artifact is not UTF-8: {path.name}") from exc


def _expected_artifacts(bundle_type: BundleType) -> tuple[str, ...]:
    match bundle_type:
        case BundleType.project_ideation:
            return IDEATION_ARTIFACTS
        case BundleType.selected_idea_plan:
            return PLAN_ARTIFACTS
        case unreachable:
            assert_never(unreachable)


def _sha256(path: Path) -> str:
    return hashlib.sha256(_read_regular_bytes(path)).hexdigest()


def _read_regular_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BundleIntegrityError(f"bundle artifact is not a regular file: {path.name}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise BundleIntegrityError(f"bundle artifact is not a regular file: {path.name}")
        return handle.read()
