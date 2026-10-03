import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from gleansight.api.models import Failure, Success
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workspaces.models import Manifest
from papers.infra.piccolo.stores import PiccoloJobQueue
from tests.workspaces.support import api, backup


@pytest.mark.parametrize("change", ["artifact", "manifest", "missing", "database"])
def test_corruption_is_rejected_before_restore(
    workspace: Path, tmp_path: Path, change: str
) -> None:
    bundle = backup(workspace)
    manifest = Manifest.model_validate_json((bundle / "manifest.json").read_bytes())
    entry = next(
        item
        for item in manifest.files
        if item.category == ("database" if change == "database" else "artifact")
    )
    target = bundle / entry.bundle_path
    if change == "manifest":
        target = bundle / "manifest.json"
    if change == "missing":
        target.unlink()
    else:
        target.write_bytes(b"changed")
    destination = tmp_path / "restore"
    result = api(workspace, approval=True).call(
        "workspaces.restore", {"backup_path": str(bundle), "destination": str(destination)}
    )
    assert isinstance(result, Failure), result
    assert not destination.exists()


def test_active_pipeline_refuses_backup(workspace: Path) -> None:
    runtime = ApiRuntime(ApiConfiguration(repo_root=workspace))
    db = runtime.paper_database
    job_id = PiccoloJobQueue().enqueue("convert", "paper-1", None, {})
    db.execute("UPDATE jobs SET status = ? WHERE job_id = ?", ["running", job_id])
    result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "conflict"
    assert not list((workspace / "output/workspace-backups").glob("*/manifest.json"))


def test_existing_sqlite_writer_refuses_backup(workspace: Path) -> None:
    runtime = ApiRuntime(ApiConfiguration(repo_root=workspace))
    with closing(sqlite3.connect(runtime.settings.data.db_path)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "conflict"


@pytest.mark.parametrize("mode", ["missing", "changed", "reference"])
def test_inconsistent_source_artifacts_refuse_backup(workspace: Path, mode: str) -> None:
    artifact = workspace / "data/blobs/md/paper-1.md"
    if mode == "missing":
        artifact.unlink()
    elif mode == "changed":
        artifact.write_text("unexpected changed markdown")
    else:
        (workspace / "evidence/source.md").unlink()
    result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


@pytest.mark.parametrize("mode", ["nonempty", "file", "symlink"])
def test_restore_does_not_overwrite_destination(workspace: Path, tmp_path: Path, mode: str) -> None:
    bundle = backup(workspace)
    destination = tmp_path / "destination"
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    (sentinel / "keep").write_text("untouched")
    if mode == "nonempty":
        destination.mkdir()
        (destination / "keep").write_text("untouched")
    elif mode == "file":
        destination.write_text("untouched")
    else:
        destination.symlink_to(sentinel, target_is_directory=True)
    result = api(workspace, approval=True).call(
        "workspaces.restore", {"backup_path": str(bundle), "destination": str(destination)}
    )
    assert isinstance(result, Failure)
    assert result.error.code == "conflict"
    assert (sentinel / "keep").read_text() == "untouched"


def test_manifest_path_traversal_is_rejected(workspace: Path, tmp_path: Path) -> None:
    bundle = backup(workspace)
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"][0]["target"] = "../escaped.sqlite"
    payload = json.dumps(manifest).encode()
    path.write_bytes(payload)
    (bundle / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest())
    result = api(workspace, approval=True).call(
        "workspaces.restore",
        {"backup_path": str(bundle), "destination": str(tmp_path / "destination")},
    )
    assert isinstance(result, Failure)
    assert not (tmp_path / "escaped.sqlite").exists()


def test_verify_operation(workspace: Path) -> None:
    result = api(workspace).call("workspaces.verify", {"backup_path": str(backup(workspace))})
    assert isinstance(result, Success)
    assert isinstance(result.data, dict) and result.data["valid"] is True


@pytest.mark.parametrize("missing", ["evidence/source.md", "data/blobs/md/paper-1.md"])
def test_missing_required_manifest_entry_is_rejected(workspace: Path, missing: str) -> None:
    bundle = backup(workspace)
    path = bundle / "manifest.json"
    manifest = Manifest.model_validate_json(path.read_bytes())
    assert any(item.target == missing for item in manifest.files)
    manifest = manifest.model_copy(
        update={"files": tuple(item for item in manifest.files if item.target != missing)}
    )
    payload = manifest.model_dump_json().encode()
    path.write_bytes(payload)
    (bundle / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest())
    result = api(workspace).call("workspaces.verify", {"backup_path": str(bundle)})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"
