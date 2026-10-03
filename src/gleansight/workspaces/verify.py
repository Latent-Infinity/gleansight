"""Verify every manifest-bound byte before a workspace may be restored."""

import hashlib
from pathlib import Path

from gleansight.workspaces.artifacts import digest, excluded
from gleansight.workspaces.database import database_state
from gleansight.workspaces.integrity import verify_references
from gleansight.workspaces.models import Manifest
from papers.domain.errors import ValidationError


def verify_backup(directory: Path) -> Manifest:
    path = directory / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ValidationError("Workspace manifest is missing or is a symlink.")
    payload = path.read_bytes()
    digest_path = directory / "manifest.sha256"
    if (
        not digest_path.is_file()
        or digest_path.read_text().strip() != hashlib.sha256(payload).hexdigest()
    ):
        raise ValidationError("Workspace manifest digest mismatch.")
    manifest = Manifest.model_validate_json(payload)
    targets: set[str] = set()
    bundles: set[str] = set()
    for entry in manifest.files:
        if entry.target in targets or entry.bundle_path in bundles:
            raise ValidationError("Workspace manifest contains duplicate paths.")
        targets.add(entry.target)
        bundles.add(entry.bundle_path)
        source = directory / entry.bundle_path
        if source.is_symlink() or not source.resolve().is_relative_to(directory.resolve()):
            raise ValidationError("Workspace artifact escapes the backup directory.")
        if excluded(Path(entry.target)) or not source.is_file():
            raise ValidationError(f"Workspace artifact is excluded or missing: {entry.target}")
        if source.stat().st_size != entry.size or digest(source) != entry.sha256:
            raise ValidationError(f"Workspace artifact digest mismatch: {entry.target}")
    for state in manifest.databases:
        entry = next(
            (
                item
                for item in manifest.files
                if item.target == state.target and item.category == "database"
            ),
            None,
        )
        if entry is None or database_state(directory / entry.bundle_path, state.target) != state:
            raise ValidationError(f"Database schema or record inventory mismatch: {state.target}")
    if not manifest.databases:
        raise ValidationError("Workspace manifest has no database snapshot.")
    verify_references(directory, manifest)
    return manifest
