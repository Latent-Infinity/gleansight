from __future__ import annotations

import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

from pydantic import JsonValue, TypeAdapter

from research.catalog.models import CatalogError, Digest
from research.financial_jepa.capacity_storage import MAX_BYTES, bounded_read


def mapping(value: JsonValue) -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_python(value)


def document(path: Path) -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_json(bounded_read(path))


def verified_artifacts(
    path: Path, names: frozenset[str]
) -> tuple[dict[str, JsonValue], dict[str, str], str]:
    if path.is_symlink() or not path.is_dir():
        raise CatalogError("Research bundle must be a regular non-symlink directory")
    if {entry.name for entry in path.iterdir()} != names | {"run-metadata.json"}:
        raise CatalogError("Research bundle has an unexpected artifact set")
    content = bounded_read(path / "run-metadata.json")
    metadata = TypeAdapter(dict[str, JsonValue]).validate_json(content)
    hashes = TypeAdapter(dict[str, Digest]).validate_python(metadata["artifact_sha256"])
    if set(hashes) != names:
        raise CatalogError("Research hash manifest does not match the workflow")
    for name, expected in hashes.items():
        raw = bounded_read(path / name)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise CatalogError(f"Research artifact hash mismatch: {name}")
        if name.endswith(".npz"):
            with ZipFile(io.BytesIO(raw)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
                    raise CatalogError("Research arrays exceed the bounded verification limit")
    if metadata.get("schema_version") != 1:
        raise CatalogError("Unsupported research manifest schema")
    return metadata, hashes, hashlib.sha256(content).hexdigest()
