from __future__ import annotations

import hashlib
import io
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from research.financial_jepa.contracts import FloatArray, ProtocolError

MAX_BYTES = 128 * 1024 * 1024


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1
    artifact_sha256: dict[str, str]


@dataclass(frozen=True, slots=True)
class LoadedCapacityBundle:
    document: dict[str, JsonValue]
    arrays: dict[str, FloatArray]


def bounded_read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ProtocolError("artifact must be a regular non-symlink file")
    with path.open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ProtocolError("artifact exceeds bounded read limit")
    return content


def write_bundle(
    path: Path, document: dict[str, JsonValue], arrays: dict[str, FloatArray], report: str = ""
) -> None:
    encoded = json.dumps(document, sort_keys=True, indent=2, allow_nan=False).encode()
    if any(
        not name or value.dtype.hasobject or not np.isfinite(value).all()
        for name, value in arrays.items()
    ):
        raise ProtocolError("capacity arrays must be finite and pickle-free")
    archive = io.BytesIO()
    np.savez(archive, allow_pickle=False, **arrays)
    contents = {
        "document.json": encoded,
        "fits.npz": archive.getvalue(),
        "report.md": report.encode(),
    }
    if any(len(content) > MAX_BYTES for content in contents.values()):
        raise ProtocolError("capacity output exceeds artifact bound")
    path.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in contents.items():
            (path / name).write_bytes(content)
        manifest = Manifest(
            artifact_sha256={
                name: hashlib.sha256(content).hexdigest() for name, content in contents.items()
            }
        )
        (path / "run-metadata.json").write_text(manifest.model_dump_json(indent=2))
    except OSError:
        shutil.rmtree(path)
        raise


def load_bundle(path: Path) -> LoadedCapacityBundle:
    manifest = Manifest.model_validate_json(bounded_read(path / "run-metadata.json"))
    if manifest.schema_version != 1 or set(manifest.artifact_sha256) != {
        "document.json",
        "fits.npz",
        "report.md",
    }:
        raise ProtocolError("capacity manifest schema disagrees")
    contents = {name: bounded_read(path / name) for name in manifest.artifact_sha256}
    if any(
        hashlib.sha256(content).hexdigest() != manifest.artifact_sha256[name]
        for name, content in contents.items()
    ):
        raise ProtocolError("capacity artifact hash mismatch")
    document = TypeAdapter(dict[str, JsonValue]).validate_json(contents["document.json"])
    with ZipFile(io.BytesIO(contents["fits.npz"])) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_BYTES:
            raise ProtocolError("capacity uncompressed arrays exceed bound")
    with np.load(io.BytesIO(contents["fits.npz"]), allow_pickle=False) as archive:
        arrays = {name: archive[name].astype(np.float64) for name in archive.files}
    if any(not np.isfinite(array).all() for array in arrays.values()):
        raise ProtocolError("capacity bundle has nonfinite arrays")
    return LoadedCapacityBundle(document, arrays)
