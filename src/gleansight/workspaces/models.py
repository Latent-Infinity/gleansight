"""Validated contracts for portable, hash-verified workspace snapshots."""

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from papers.domain.errors import ValidationError


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Resource(Record):
    source: Path
    target: str

    @field_validator("target")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValidationError(f"Unsafe workspace-relative path: {value}")
        return value


class Workspace(Record):
    root: Path
    databases: tuple[Resource, ...]
    blob_roots: tuple[Resource, ...] = Field(min_length=4, max_length=4)
    external_inputs: tuple[Resource, ...] = ()
    indexes: tuple[Resource, ...]
    data_paths: dict[str, str]
    nsqd_db: str
    nsqd_index: str
    embedding_model: str
    embedding_dimension: int
    text_slice_strategy: str

    @field_validator("nsqd_db", "nsqd_index")
    @classmethod
    def safe_location(cls, value: str) -> str:
        return Resource.safe_relative_path(value)

    @field_validator("data_paths")
    @classmethod
    def safe_data_paths(cls, values: dict[str, str]) -> dict[str, str]:
        required = {
            "root",
            "db_path",
            "blobs_dir",
            "blobs_pdf_dir",
            "blobs_md_dir",
            "blobs_analysis_dir",
            "lancedb_dir",
        }
        if values.keys() != required:
            raise ValidationError("Workspace data paths do not match the supported layout.")
        return {key: Resource.safe_relative_path(value) for key, value in values.items()}


class FileEntry(Resource):
    bundle_path: str
    sha256: str
    size: int
    category: Literal["database", "artifact", "archive", "generated"]

    @field_validator("target")
    @classmethod
    def reserved_targets(cls, value: str) -> str:
        if value in {".gleansight-restore.toml", "workspace-restore.json"}:
            raise ValidationError("Workspace artifact collides with restore metadata.")
        return value

    @field_validator("bundle_path")
    @classmethod
    def safe_bundle_path(cls, value: str) -> str:
        return Resource.safe_relative_path(value)


class TableState(Record):
    name: str
    rows: int


class DatabaseState(Record):
    target: str
    user_version: int
    migrations: tuple[str, ...]
    schema_sha256: str
    tables: tuple[TableState, ...]


class Manifest(Record):
    schema_version: Literal[1] = 1
    created_at: str
    source_root: Path
    workspace: Workspace
    files: tuple[FileEntry, ...]
    databases: tuple[DatabaseState, ...]
    index_disposition: Literal["rebuild_required"] = "rebuild_required"
    excluded: tuple[str, ...] = (
        "credentials",
        "environment files",
        "provider caches",
        "vector indexes",
    )


class BackupResult(Record):
    backup_path: Path
    manifest_path: Path


class RestoreResult(Record):
    destination: Path
    config_path: Path
    nsqd_db: Path
    nsqd_index: Path
    index_disposition: Literal["rebuild_required"] = "rebuild_required"
