from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nsqd.infrastructure.workflow_output import create_run_directory
from research.financial_jepa.contracts import Deadline, JsonValue, ProtocolError


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    protocol: Mapping[str, JsonValue]
    source_metadata: Mapping[str, JsonValue]
    results: Mapping[str, JsonValue]
    report: str
    run_metadata: Mapping[str, JsonValue]


def _json_bytes(value: Mapping[str, JsonValue]) -> bytes:
    try:
        rendered = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("artifact contains a non-JSON or nonfinite value") from exc
    return (rendered + "\n").encode()


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


def write_bundle(
    repo_root: Path,
    output_dir: Path | None,
    bundle: ArtifactBundle,
    deadline: Deadline | None = None,
) -> Path:
    run_root = create_run_directory(repo_root, "financial-jepa", output_dir)
    try:
        if deadline is not None:
            deadline.check()
        artifacts = {
            "protocol.json": _json_bytes(bundle.protocol),
            "source-metadata.json": _json_bytes(bundle.source_metadata),
            "results.json": _json_bytes(bundle.results),
            "report.md": bundle.report.encode(),
        }
        for name, content in artifacts.items():
            if deadline is not None:
                deadline.check()
            _atomic_write(run_root / name, content)
        metadata: dict[str, JsonValue] = {
            **bundle.run_metadata,
            "schema_version": 1,
            "workflow": "financial-jepa",
            "run_id": run_root.name,
            "completion_marker_write_started_at_utc": datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "completion_state": "complete",
            "artifact_sha256": {
                name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()
            },
        }
        if deadline is not None:
            deadline.check()
        _atomic_write(run_root / "run-metadata.json", _json_bytes(metadata))
        if deadline is not None:
            deadline.check()
    except (OSError, ProtocolError, TimeoutError):
        shutil.rmtree(run_root)
        raise
    return run_root
