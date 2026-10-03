"""Restore verified bytes atomically, rebasing only operational path columns."""

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import JsonValue, TypeAdapter

from gleansight.workspaces.artifacts import digest
from gleansight.workspaces.database import quote_identifier, tables
from gleansight.workspaces.models import Manifest, RestoreResult
from gleansight.workspaces.references import path_key
from gleansight.workspaces.verify import verify_backup
from papers.domain.errors import ConflictError, ValidationError


def _rebase_database(path: Path, manifest: Manifest, destination: Path) -> None:
    locations = {str(item.source): str(destination / item.target) for item in manifest.files}
    for item in manifest.files:
        source_parent = item.source.parent
        target_parent = (destination / item.target).parent
        while target_parent != destination and target_parent.is_relative_to(destination):
            locations[str(source_parent)] = str(target_parent)
            source_parent, target_parent = source_parent.parent, target_parent.parent
    with closing(sqlite3.connect(path)) as connection, connection:
        names = tables(connection)
        if "jobs" in names:
            for job_id, encoded in connection.execute(
                "SELECT job_id, payload_json FROM jobs WHERE status = 'queued' "
                "AND type IN ('download', 'convert')"
            ):
                payload = TypeAdapter(dict[str, JsonValue]).validate_json(encoded)
                original = payload.get("source_path")
                match original:  # noqa: MATCH_OK - rewrite only mapped operational strings
                    case str() if original in locations:
                        payload["source_path"] = locations[original]
                        connection.execute(
                            "UPDATE jobs SET payload_json = ? WHERE job_id = ?",
                            (json.dumps(payload), job_id),
                        )
                    case _:
                        pass
        for table in names:
            for column in (
                row[1]
                for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})")
            ):
                if not path_key(column):
                    continue
                for original, restored in locations.items():
                    connection.execute(
                        f"UPDATE {quote_identifier(table)} SET {quote_identifier(column)} = ? "
                        f"WHERE {quote_identifier(column)} = ?",
                        (restored, original),
                    )


def restore_workspace(backup_path: Path, destination: Path) -> RestoreResult:
    manifest = verify_backup(backup_path)
    if destination.is_symlink() or (
        destination.exists() and (not destination.is_dir() or any(destination.iterdir()))
    ):
        raise ConflictError("Restore destination must be an empty directory or a new path.")
    destination = destination.absolute()
    if destination.resolve().is_relative_to(backup_path.resolve()):
        raise ValidationError("Restore destination cannot be inside the backup.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".restore-", dir=destination.parent) as staging:
        stage = Path(staging)
        for entry in manifest.files:
            target = stage / entry.target
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(backup_path / entry.bundle_path, target)
            if digest(target) != entry.sha256:
                raise ValidationError(f"Backup changed while restoring: {entry.target}")
        for state in manifest.databases:
            _rebase_database(stage / state.target, manifest, destination)
        config = "[data]\n" + "\n".join(
            f"{key} = {json.dumps(value)}" for key, value in manifest.workspace.data_paths.items()
        )
        config += "\n\n[embeddings]\n"
        config += f"model = {json.dumps(manifest.workspace.embedding_model)}\n"
        config += f"dimension = {manifest.workspace.embedding_dimension}\n"
        config += f"text_slice_strategy = {json.dumps(manifest.workspace.text_slice_strategy)}\n"
        (stage / ".gleansight-restore.toml").write_text(config, encoding="utf-8")
        (stage / "workspace-restore.json").write_text(
            json.dumps(
                {
                    "source_manifest": str(backup_path / "manifest.json"),
                    "index_disposition": "rebuild_required",
                    "nsqd_db": manifest.workspace.nsqd_db,
                    "nsqd_index": manifest.workspace.nsqd_index,
                    "authority_json": "preserved_byte_for_byte",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if destination.exists() and any(destination.iterdir()):
            raise ConflictError("Restore destination became nonempty before publication.")
        stage.replace(destination)
    return RestoreResult(
        destination=destination,
        config_path=destination / ".gleansight-restore.toml",
        nsqd_db=destination / manifest.workspace.nsqd_db,
        nsqd_index=destination / manifest.workspace.nsqd_index,
    )
