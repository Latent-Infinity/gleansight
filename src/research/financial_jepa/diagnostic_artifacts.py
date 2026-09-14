from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import uuid
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from nsqd.infrastructure.workflow_output import create_run_directory
from research.financial_jepa.contracts import Deadline, JsonValue, ProtocolError
from research.financial_jepa.diagnostic_validation import validate_date_arrays

type NumericArray = NDArray[np.number] | NDArray[np.str_]

ARTIFACT_FILES = (
    "protocol.json",
    "source-metadata.json",
    "results.json",
    "states.npz",
    "ridge.npz",
    "validation.npz",
    "report.md",
)


@dataclass(frozen=True, slots=True)
class DiagnosticBundle:
    protocol: Mapping[str, JsonValue]
    source_metadata: Mapping[str, JsonValue]
    results: Mapping[str, JsonValue]
    states: Mapping[str, NumericArray]
    ridge: Mapping[str, NumericArray]
    validation: Mapping[str, NumericArray]
    report: str
    run_metadata: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LoadedDiagnosticBundle:
    protocol: dict[str, JsonValue]
    source_metadata: dict[str, JsonValue]
    results: dict[str, JsonValue]
    states: dict[str, NumericArray]
    ridge: dict[str, NumericArray]
    validation: dict[str, NumericArray]


def _json_bytes(value: Mapping[str, JsonValue]) -> bytes:
    try:
        rendered = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("diagnostic artifact contains invalid JSON") from exc
    return (rendered + "\n").encode()


def _npz_bytes(values: Mapping[str, NumericArray]) -> bytes:
    if not values:
        raise ProtocolError("diagnostic NPZ artifact is empty")
    for name, value in values.items():
        if not name or value.dtype.hasobject:
            raise ProtocolError("diagnostic NPZ keys and arrays must be pickle-free")
        if value.dtype.kind not in "biufSU":
            raise ProtocolError("diagnostic NPZ array dtype is not numeric or fixed Unicode")
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in values.items():
            encoded = io.BytesIO()
            np.save(encoded, value, allow_pickle=False)
            archive.writestr(f"{name}.npy", encoded.getvalue())
    return output.getvalue()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_diagnostic_bundle(
    repo_root: Path,
    output_dir: Path | None,
    bundle: DiagnosticBundle,
    deadline: Deadline,
) -> Path:
    run_root = create_run_directory(repo_root, "financial-jepa-diagnostics", output_dir)
    repository = repo_root.resolve()
    diagnostic_namespace = repository / "output/financial-jepa-diagnostics"
    resolved_run = run_root.resolve()
    if resolved_run.is_relative_to(repository) and not resolved_run.is_relative_to(
        diagnostic_namespace
    ):
        shutil.rmtree(run_root)
        raise ProtocolError("diagnostic output must use the financial-jepa-diagnostics namespace")
    try:
        deadline.check()
        contents = {
            "protocol.json": _json_bytes(bundle.protocol),
            "source-metadata.json": _json_bytes(bundle.source_metadata),
            "results.json": _json_bytes(bundle.results),
            "states.npz": _npz_bytes(bundle.states),
            "ridge.npz": _npz_bytes(bundle.ridge),
            "validation.npz": _npz_bytes(bundle.validation),
            "report.md": bundle.report.encode(),
        }
        for name in ARTIFACT_FILES:
            deadline.check()
            _atomic_write(run_root / name, contents[name])
        metadata: dict[str, JsonValue] = {
            **bundle.run_metadata,
            "schema_version": 1,
            "workflow": "financial-jepa-diagnostics",
            "run_id": run_root.name,
            "completion_state": "complete",
            "completion_marker_write_started_at_utc": datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "artifact_sha256": {
                name: hashlib.sha256(contents[name]).hexdigest() for name in ARTIFACT_FILES
            },
        }
        deadline.check()
        _atomic_write(run_root / "run-metadata.json", _json_bytes(metadata))
        deadline.check()
    except (OSError, ProtocolError, TimeoutError):
        shutil.rmtree(run_root)
        raise
    return run_root


def _json_mapping(content: bytes, expected: frozenset[str]) -> dict[str, JsonValue]:
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("diagnostic JSON artifact is malformed") from exc
    if not isinstance(value, dict) or set(value) != expected:
        raise ProtocolError("diagnostic JSON artifact has unknown or missing keys")
    return value


def _load_npz(content: bytes, expected: Mapping[str, JsonValue]) -> dict[str, NumericArray]:
    try:
        with np.load(io.BytesIO(content), allow_pickle=False) as archive:
            if set(archive.files) != set(expected):
                raise ProtocolError("diagnostic NPZ artifact has unknown or missing keys")
            values = {name: archive[name].copy() for name in archive.files}
    except ProtocolError:
        raise
    except (OSError, ValueError) as exc:
        raise ProtocolError("diagnostic NPZ artifact is invalid or pickle-backed") from exc
    if any(value.dtype.hasobject or value.dtype.kind not in "biufSU" for value in values.values()):
        raise ProtocolError("diagnostic NPZ artifact contains a forbidden dtype")
    for name, value in values.items():
        specification = expected[name]
        if not isinstance(specification, dict):
            raise ProtocolError("diagnostic array specification is invalid")
        if set(specification) != {"shape", "dtype"}:
            raise ProtocolError("diagnostic array specification has unknown keys")
        if specification["shape"] != list(value.shape) or specification["dtype"] != value.dtype.str:
            raise ProtocolError("diagnostic NPZ shape or dtype does not match manifest")
    return values


def load_diagnostic_bundle(run_root: Path) -> LoadedDiagnosticBundle:
    metadata_content = (run_root / "run-metadata.json").read_bytes()
    metadata = _json_mapping(
        metadata_content,
        frozenset(
            {
                "schema_version",
                "workflow",
                "run_id",
                "completion_state",
                "artifact_sha256",
                "runtime",
                "code_identity",
                "protocol_sha256",
                "source_metadata_sha256",
                "planned_fit_count",
                "observed_fit_count",
                "planned_epoch_count",
                "observed_epoch_count",
                "completion_marker_write_started_at_utc",
            }
        ),
    )
    hashes = metadata["artifact_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != set(ARTIFACT_FILES):
        raise ProtocolError("diagnostic hash manifest is incomplete")
    contents = {name: (run_root / name).read_bytes() for name in ARTIFACT_FILES}
    if any(hashlib.sha256(contents[name]).hexdigest() != hashes[name] for name in ARTIFACT_FILES):
        raise ProtocolError("diagnostic artifact hash mismatch")
    if hashlib.sha256(contents["protocol.json"]).hexdigest() != metadata["protocol_sha256"]:
        raise ProtocolError("diagnostic protocol identity mismatch")
    if (
        hashlib.sha256(contents["source-metadata.json"]).hexdigest()
        != metadata["source_metadata_sha256"]
    ):
        raise ProtocolError("diagnostic source identity mismatch")
    protocol = _json_mapping(
        contents["protocol.json"],
        frozenset(
            {
                "protocol_version",
                "status",
                "dataset",
                "window",
                "training",
                "methods",
                "interpretation",
            }
        ),
    )
    source = _json_mapping(
        contents["source-metadata.json"],
        frozenset(
            {
                "publisher",
                "dataset_title",
                "landing_url",
                "api_url_template",
                "license_expression",
                "copyright_assessment",
                "transformation",
                "selected_fields",
                "copyright_basis_url",
                "methodology_url",
                "endorsement",
                "yearly_responses",
                "dropped_missing_dates",
                "missing_tenor_rows",
            }
        ),
    )
    results = _json_mapping(
        contents["results.json"],
        frozenset("status date_sha256 methods seeds aggregates persistence array_manifest".split()),
    )
    manifest = results["array_manifest"]
    if not isinstance(manifest, dict) or set(manifest) != {
        "states.npz",
        "ridge.npz",
        "validation.npz",
    }:
        raise ProtocolError("diagnostic array manifest is invalid")
    expected = {name: keys for name, keys in manifest.items() if isinstance(keys, dict)}
    if set(expected) != set(manifest):
        raise ProtocolError("diagnostic array manifest keys are invalid")
    validation = _load_npz(contents["validation.npz"], expected["validation.npz"])
    validate_date_arrays(validation)
    return LoadedDiagnosticBundle(
        protocol,
        source,
        results,
        _load_npz(contents["states.npz"], expected["states.npz"]),
        _load_npz(contents["ridge.npz"], expected["ridge.npz"]),
        validation,
    )
