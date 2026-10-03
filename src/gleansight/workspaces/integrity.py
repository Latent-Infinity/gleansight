"""Validate referenced bytes against the database captured in the same backup."""

from contextlib import closing
from pathlib import Path

import xxhash

from gleansight.workspaces.database import reader, tables
from gleansight.workspaces.models import Manifest
from gleansight.workspaces.references import artifact_references, database_references
from nsqd.domain.artifact_paths import resolve_artifact_path
from papers.domain.errors import ValidationError


def verify_references(directory: Path, manifest: Manifest) -> None:
    sources = {entry.source: entry for entry in manifest.files}

    def require(reference: str, base: Path) -> None:
        raw = Path(reference)
        candidates = (
            (raw,)
            if raw.is_absolute()
            else (base / raw, resolve_artifact_path(manifest.source_root, raw))
        )
        if any(
            source == candidate or source.is_relative_to(candidate)
            for source in sources
            for candidate in candidates
        ):
            return
        if not raw.is_absolute() and any(
            source.as_posix().endswith("/" + reference) for source in sources
        ):
            return
        raise ValidationError(f"Backup is missing a required referenced artifact: {reference}")

    for entry in manifest.files:
        if entry.category == "database":
            with closing(reader(directory / entry.bundle_path)) as connection:
                for reference in database_references(connection):
                    require(reference, manifest.source_root)
                if "papers" not in tables(connection):
                    continue
                for paper_id, pdf_hash, md_hash in connection.execute(
                    "SELECT paper_id, pdf_fingerprint_xxh64, md_fingerprint_xxh64 FROM papers"
                ):
                    for fingerprint, source in (
                        (
                            pdf_hash,
                            manifest.workspace.blob_roots[1].source / f"{pdf_hash}.pdf",
                        ),
                        (
                            md_hash,
                            manifest.workspace.blob_roots[2].source / f"{paper_id}.md",
                        ),
                    ):
                        if not fingerprint:
                            continue
                        artifact = sources.get(source)
                        if artifact is None:
                            raise ValidationError(f"Backup is missing a paper blob: {source}")
                        hasher = xxhash.xxh64()
                        with (directory / artifact.bundle_path).open("rb") as handle:
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                hasher.update(chunk)
                        if hasher.hexdigest() != fingerprint:
                            raise ValidationError(
                                f"Backup paper blob fingerprint mismatch: {source}"
                            )
        else:
            for reference in artifact_references(directory / entry.bundle_path):
                require(reference, entry.source.parent)
