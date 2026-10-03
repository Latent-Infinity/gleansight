"""Coordinate databases and referenced artifacts into an immutable backup."""

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from gleansight.workspaces.artifacts import collect_artifacts, digest, file_entry, target_path
from gleansight.workspaces.database import database_state, guarded_databases, snapshot_database
from gleansight.workspaces.inputs import capture_inputs
from gleansight.workspaces.models import BackupResult, FileEntry, Manifest, Workspace
from gleansight.workspaces.verify import verify_backup
from papers.domain.errors import ConflictError


def backup_workspace(workspace: Workspace, output_root: Path) -> BackupResult:
    output_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    destination = output_root / (now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8])
    with TemporaryDirectory(prefix=".capture-", dir=output_root) as staging:
        stage = Path(staging)
        entries: list[FileEntry] = []
        with guarded_databases(tuple(item.source for item in workspace.databases)) as guards:
            workspace = capture_inputs(workspace, guards)
            required = collect_artifacts(workspace, guards)
            (stage / "databases").mkdir()
            states = []
            for number, resource in enumerate(workspace.databases):
                bundle_path = f"databases/{number}.sqlite"
                copied = stage / bundle_path
                snapshot_database(resource.source, copied)
                entries.append(
                    FileEntry(
                        source=resource.source,
                        target=resource.target,
                        bundle_path=bundle_path,
                        sha256=digest(copied),
                        size=copied.stat().st_size,
                        category="database",
                    )
                )
                states.append(database_state(copied, resource.target))
            for source in required:
                copied = stage / "files" / target_path(source, workspace)
                copied.parent.mkdir(parents=True, exist_ok=True)
                before = digest(source)
                shutil.copyfile(source, copied)
                entry = file_entry(source, copied, workspace)
                if before != entry.sha256 or digest(source) != before:
                    raise ConflictError(f"Artifact changed during workspace backup: {source}")
                entries.append(entry)
            manifest = Manifest(
                created_at=now.isoformat(),
                source_root=workspace.root,
                workspace=workspace,
                files=tuple(entries),
                databases=tuple(states),
            )
            content = (manifest.model_dump_json(indent=2) + "\n").encode()
            (stage / "manifest.json").write_bytes(content)
            (stage / "manifest.sha256").write_text(hashlib.sha256(content).hexdigest() + "\n")
            verify_backup(stage)
        stage.rename(destination)
    return BackupResult(backup_path=destination, manifest_path=destination / "manifest.json")
