from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class PipelineStage(StrEnum):
    imported = "imported"
    downloaded = "downloaded"
    converted = "converted"
    embedded = "embedded"
    analyzed = "analyzed"


class PipelineHealth(StrEnum):
    ok = "ok"
    error = "error"


class JobType(StrEnum):
    discover = "discover"
    download = "download"
    convert = "convert"
    embed = "embed"
    analyze = "analyze"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class OutputFormat(StrEnum):
    yaml_block = "yaml_block"
    json_block = "json_block"
    json_only = "json_only"
    markdown_only = "markdown_only"


class TagType(StrEnum):
    subject = "subject"
    method = "method"
    application = "application"
    custom = "custom"


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    source: str
    source_paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    external_ids: dict[str, str] | None = None
    rejected_at: datetime | None = None
    imported_paper_id: str | None = None
    imported_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("title")
    @classmethod
    def _title_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title is required")
        return value


class Paper(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None

    pipeline_stage: PipelineStage
    pipeline_health: PipelineHealth
    last_error_job_id: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_error_at: datetime | None = None

    pdf_fingerprint_xxh64: str | None = None
    md_fingerprint_xxh64: str | None = None
    md_source_pdf_fingerprint_xxh64: str | None = None
    md_converter: str | None = None
    md_converter_version: str | None = None

    embedding_model: str | None = None
    embedding_dimension: int | None = None
    text_slice_strategy: str | None = None
    embedded_from_md_fingerprint_xxh64: str | None = None

    created_at: datetime
    updated_at: datetime

    @field_validator("title")
    @classmethod
    def _title_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title is required")
        return value


class PaperExternalId(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_external_id_id: str
    paper_id: str
    kind: str
    value: str
    created_at: datetime


class Project(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class Tag(BaseModel):
    model_config = ConfigDict(frozen=True)

    tag_id: str
    name: str
    type: TagType
    created_at: datetime
    updated_at: datetime


class PaperProject(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_id: str
    project_id: str
    label: str | None = None
    created_at: datetime


class PaperTag(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_id: str
    tag_id: str
    confidence: float | None = None
    created_at: datetime


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_id: str
    name: str
    description: str | None = None
    domain: str | None = None
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class PromptVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_version_id: str
    prompt_id: str
    version: int
    body: str
    output_format: OutputFormat
    extraction_schema_json: dict[str, JsonValue] | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _validate_output_contract(self) -> PromptVersion:
        if (
            self.output_format is OutputFormat.markdown_only
            and self.extraction_schema_json is not None
        ):
            raise ValueError("markdown_only output cannot define extraction_schema_json")
        return self


class EndpointProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str
    name: str
    base_url: str
    default_model: str | None = None
    is_active: bool = True
    input_price_per_1k_tokens: float | None = None
    output_price_per_1k_tokens: float | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("base_url")
    @classmethod
    def _base_url_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("base_url is required")
        return value


class AnalysisRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    paper_id: str
    prompt_version_id: str
    profile_id: str
    model_name: str
    output_blob_path_md: str | None = None
    output_blob_path_json: str | None = None
    validation_issues: list[dict[str, Any]] | None = None
    error_message: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    type: JobType
    status: JobStatus
    paper_id: str | None
    run_id: str | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate_run_id(self) -> JobRecord:
        if self.type is JobType.analyze and self.run_id is None:
            raise ValueError("analyze jobs require run_id")
        return self


class Extraction(BaseModel):
    model_config = ConfigDict(frozen=True)

    extraction_id: str
    run_id: str
    paper_id: str
    prompt_version_id: str
    entity_type: str = "paper"
    entity_ref: str | None = None
    field_path: str
    value_text: str | None = None
    value_numeric: float | None = None
    value_boolean: int | None = None
    created_at: datetime
