"""Collect required immutable bytes while excluding credentials and caches."""

import hashlib
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import xxhash

from gleansight.workspaces.models import FileEntry, Workspace
from gleansight.workspaces.references import artifact_references, database_references
from nsqd.domain.artifact_paths import resolve_artifact_path
from papers.domain.errors import ValidationError


def excluded(path: Path) -> bool:
    return any(
        Path(part).stem
        in {
            ".git",
            ".cache",
            "__pycache__",
            "node_modules",
            "provider_cache",
            "provider_caches",
            "credentials",
            "keys",
            "id_rsa",
            "id_ed25519",
            "api_key",
            ".ssh",
            ".aws",
            "secrets",
            "workspace-backups",
        }
        or part == ".env"
        or part.startswith(".env.")
        for part in path.parts
    ) or (path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"})


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def target_path(path: Path, workspace: Workspace) -> str:
    for resource in workspace.external_inputs:
        if path == resource.source:
            return resource.target
    if path.is_relative_to(workspace.root):
        return str(path.relative_to(workspace.root))
    for resource in sorted(
        workspace.blob_roots, key=lambda item: len(item.source.parts), reverse=True
    ):
        if path.is_relative_to(resource.source):
            return str(Path(resource.target) / path.relative_to(resource.source))
    raise ValidationError(f"Artifact is outside configured workspace resources: {path}")


def collect_artifacts(
    workspace: Workspace, connections: Iterable[sqlite3.Connection]
) -> tuple[Path, ...]:
    found: set[Path] = set()

    def add(path: Path, *, required: bool) -> None:
        if excluded(path) or any(path.is_relative_to(item.source) for item in workspace.indexes):
            if required:
                raise ValidationError(f"Required artifact is excluded from backup: {path}")
            return
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValidationError(f"Artifact symlinks are not supported: {path}")
        if not path.exists():
            if required:
                raise ValidationError(f"Required artifact is missing: {path}")
            return
        target_path(path, workspace)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_symlink():
                    raise ValidationError(f"Artifact symlinks are not supported: {child}")
                if child.is_file():
                    add(child, required=False)
            return
        found.add(path)

    for root in (*[item.source for item in workspace.blob_roots], workspace.root / "evidence"):
        add(root, required=False)

    def resolve(reference: str, relative_to: Path) -> None:
        raw = Path(reference)
        candidates = (
            [raw]
            if raw.is_absolute()
            else [relative_to / raw, resolve_artifact_path(workspace.root, raw)]
        )
        existing = next((path for path in candidates if path.exists()), None)
        if existing is None and not raw.is_absolute():
            existing = next(
                (path for path in sorted(found) if path.as_posix().endswith("/" + reference)), None
            )
        add((existing or candidates[0]).absolute(), required=True)

    for connection in connections:
        for reference in database_references(connection):
            resolve(reference, workspace.root)
        if "papers" in tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        ):
            for paper_id, pdf_hash, md_hash in connection.execute(
                "SELECT paper_id, pdf_fingerprint_xxh64, md_fingerprint_xxh64 FROM papers"
            ):
                for fingerprint, source in (
                    (pdf_hash, workspace.blob_roots[1].source / f"{pdf_hash}.pdf"),
                    (md_hash, workspace.blob_roots[2].source / f"{paper_id}.md"),
                ):
                    if fingerprint:
                        add(source, required=True)
                        hasher = xxhash.xxh64()
                        with source.open("rb") as handle:
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                hasher.update(chunk)
                        if hasher.hexdigest() != fingerprint:
                            raise ValidationError(f"Paper artifact fingerprint mismatch: {source}")
    inspected: set[Path] = set()
    while pending := found - inspected:
        for path in sorted(pending):
            inspected.add(path)
            for reference in artifact_references(path):
                resolve(reference, path.parent)
    return tuple(sorted(found))


def file_entry(source: Path, copied: Path, workspace: Workspace) -> FileEntry:
    target = target_path(source, workspace)
    category = "artifact"
    if target.startswith("evidence/archive/"):
        category = "archive"
    elif target.startswith("output/"):
        category = "generated"
    return FileEntry.model_validate(
        {
            "source": source,
            "target": target,
            "bundle_path": "files/" + target,
            "sha256": digest(copied),
            "size": copied.stat().st_size,
            "category": category,
        }
    )
