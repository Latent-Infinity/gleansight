"""Registry-backed workspace backup, verification and approved restore."""

from pathlib import Path

from pydantic import JsonValue

from gleansight.api.models import EmptyRequest, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from gleansight.workspaces.backup import backup_workspace
from gleansight.workspaces.layout import workspace_layout
from gleansight.workspaces.restore import restore_workspace
from gleansight.workspaces.verify import verify_backup


class BackupPath(Request):
    backup_path: Path


class Restore(BackupPath):
    destination: Path


def backup(runtime: ApiRuntime, _: EmptyRequest) -> JsonValue:
    result = backup_workspace(
        workspace_layout(runtime), runtime.repo_root / "output/workspace-backups"
    )
    return json_result(result.model_dump(mode="json"))


def verify(runtime: ApiRuntime, request: BackupPath) -> JsonValue:
    manifest = verify_backup(runtime.resolve(request.backup_path))
    return {"valid": True, "files": len(manifest.files), "index_disposition": "rebuild_required"}


def restore(runtime: ApiRuntime, request: Restore) -> JsonValue:
    runtime.require_approval()
    destination = (
        request.destination
        if request.destination.is_absolute()
        else (runtime.repo_root / request.destination)
    )
    result = restore_workspace(runtime.resolve(request.backup_path), destination)
    return json_result(result.model_dump(mode="json"))


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "workspaces.backup",
            "Back up idle authoritative workspace state with hashes.",
            EmptyRequest,
            backup,
            ("write",),
        ),
        Operation("workspaces.verify", "Verify a workspace backup before use.", BackupPath, verify),
        Operation(
            "workspaces.restore",
            "Restore into an empty workspace; approval required.",
            Restore,
            restore,
            ("write", "approval"),
        ),
    )
