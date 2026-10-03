"""Preserve explicitly queued external PDF inputs without scanning external directories."""

import hashlib
import sqlite3
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from gleansight.workspaces.artifacts import excluded
from gleansight.workspaces.database import tables
from gleansight.workspaces.models import Resource, Workspace
from papers.domain.errors import ValidationError


def capture_inputs(workspace: Workspace, connections: tuple[sqlite3.Connection, ...]) -> Workspace:
    inputs: dict[Path, Resource] = {}
    for connection in connections:
        if "jobs" not in tables(connection):
            continue
        for (encoded,) in connection.execute(
            "SELECT payload_json FROM jobs WHERE status = 'queued' "
            "AND type IN ('download', 'convert')"
        ):
            payload = TypeAdapter(dict[str, JsonValue]).validate_json(encoded)
            reference = payload.get("source_path")
            if reference is None:
                continue
            source = Path(TypeAdapter(str).validate_python(reference))
            if not source.is_absolute():
                source = workspace.root / source
            if source.is_relative_to(workspace.root) or any(
                source.is_relative_to(root.source) for root in workspace.blob_roots
            ):
                continue
            if excluded(source) or source.suffix.lower() != ".pdf" or not source.is_file():
                raise ValidationError(
                    "External queued inputs must be existing nonsecret PDF files."
                )
            if any(path.is_symlink() for path in (source, *source.parents)):
                raise ValidationError("External queued input symlinks are not supported.")
            with source.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise ValidationError("External queued input is not a PDF file.")
            identity = hashlib.sha256(str(source).encode()).hexdigest()
            inputs[source] = Resource(
                source=source, target=f"external-inputs/{identity}/{source.name}"
            )
    return workspace.model_copy(update={"external_inputs": tuple(inputs.values())})
