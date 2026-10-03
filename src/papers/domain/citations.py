"""Typed metadata snapshots for citation and extraction interchange."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from papers.domain.errors import ValidationError

type ExportFormat = Literal["bibtex", "ris", "csv", "extractions"]


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExportSelection(Snapshot):
    paper_ids: tuple[str, ...] = ()
    project_id: str | None = None
    format: ExportFormat = "bibtex"

    @model_validator(mode="after")
    def exclusive_scope(self) -> ExportSelection:
        if bool(self.paper_ids) == bool(self.project_id):
            raise ValidationError("Choose paper_ids or project_id, exclusively.")
        if any(not item.strip() for item in self.paper_ids):
            raise ValidationError("Paper IDs must be nonempty.")
        return self


class Citation(Snapshot):
    paper_id: str
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    external_ids: dict[str, str] = {}
    md_fingerprint_xxh64: str | None = None

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name in ("authors", "title", "year", "venue", "doi") if not getattr(self, name)
        )


class ArtifactIdentity(Snapshot):
    path: str
    sha256: str | None
    status: Literal["available", "missing"]


class RunIdentity(Snapshot):
    run_id: str
    paper_id: str
    prompt_version_id: str
    model_name: str
    output_blob_path_md: str | None = None
    output_blob_path_json: str | None = None
    artifacts: tuple[ArtifactIdentity, ...] = ()


class ExtractionRow(Snapshot):
    extraction_id: str
    paper_id: str
    run_id: str
    prompt_version_id: str
    entity_type: str
    entity_ref: str | None
    field_path: str
    value: JsonValue
    source_locator: str | None = None
    source_locator_status: Literal["unavailable"] = "unavailable"
    source_locator_reason: str = "No passage locator is stored for this extraction."


class ExportManifest(Snapshot):
    schema_version: Literal[1] = 1
    export_id: str
    created_at: str
    selection: ExportSelection
    paper_ids: tuple[str, ...]
    papers: tuple[Citation, ...]
    runs: tuple[RunIdentity, ...]
    missing_fields: dict[str, tuple[str, ...]]
    artifact: ArtifactIdentity
