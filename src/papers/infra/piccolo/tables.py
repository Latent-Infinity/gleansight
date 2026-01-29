from __future__ import annotations

from datetime import UTC, datetime

from piccolo.columns import Boolean, Integer, Numeric, Text, Timestamptz, Varchar
from piccolo.table import Table


def _now() -> datetime:
    return datetime.now(UTC)


class Candidate(Table, tablename="candidates"):
    candidate_id = Varchar(primary_key=True)
    source = Varchar()
    source_paper_id = Varchar()
    title = Text()
    year = Integer(null=True)
    venue = Varchar(null=True)
    authors_json = Text(default="[]")
    abstract = Text(null=True)
    external_ids_json = Text(null=True)
    rejected_at = Timestamptz(null=True)
    imported_paper_id = Varchar(null=True)
    imported_at = Timestamptz(null=True)
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class Paper(Table, tablename="papers"):
    paper_id = Varchar(primary_key=True)
    title = Text()
    year = Integer(null=True)
    venue = Varchar(null=True)
    authors_json = Text(default="[]")
    abstract = Text(null=True)
    pipeline_stage = Varchar()
    pipeline_health = Varchar()
    last_error_job_id = Varchar(null=True)
    last_error_code = Varchar(null=True)
    last_error_message = Text(null=True)
    last_error_at = Timestamptz(null=True)
    pdf_fingerprint_xxh64 = Varchar(null=True)
    md_fingerprint_xxh64 = Varchar(null=True)
    md_source_pdf_fingerprint_xxh64 = Varchar(null=True)
    md_converter = Varchar(null=True)
    md_converter_version = Varchar(null=True)
    embedding_model = Varchar(null=True)
    embedding_dimension = Integer(null=True)
    text_slice_strategy = Varchar(null=True)
    embedded_from_md_fingerprint_xxh64 = Varchar(null=True)
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class PaperExternalId(Table, tablename="paper_external_ids"):
    paper_external_id_id = Varchar(primary_key=True)
    paper_id = Varchar()
    kind = Varchar()
    value = Varchar()
    created_at = Timestamptz(default=_now)


class Project(Table, tablename="projects"):
    project_id = Varchar(primary_key=True)
    name = Varchar(unique=True)
    description = Text(null=True)
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class Tag(Table, tablename="tags"):
    tag_id = Varchar(primary_key=True)
    name = Varchar(unique=True)
    type = Varchar()
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class PaperProject(Table, tablename="paper_projects"):
    paper_id = Varchar()
    project_id = Varchar()
    label = Varchar(null=True)
    created_at = Timestamptz(default=_now)


class PaperTag(Table, tablename="paper_tags"):
    paper_id = Varchar()
    tag_id = Varchar()
    confidence = Numeric(null=True)
    created_at = Timestamptz(default=_now)


class Prompt(Table, tablename="prompts"):
    prompt_id = Varchar(primary_key=True)
    name = Varchar()
    description = Text(null=True)
    domain = Varchar(null=True)
    tags_json = Text(null=True)
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class PromptVersion(Table, tablename="prompt_versions"):
    prompt_version_id = Varchar(primary_key=True)
    prompt_id = Varchar()
    version = Integer()
    body = Text()
    output_format = Varchar()
    extraction_schema_json = Text(null=True)
    created_at = Timestamptz(default=_now)


class EndpointProfile(Table, tablename="endpoint_profiles"):
    profile_id = Varchar(primary_key=True)
    name = Varchar(unique=True)
    base_url = Varchar()
    default_model = Varchar(null=True)
    is_active = Boolean(default=True)
    input_price_per_1k_tokens = Numeric(null=True)
    output_price_per_1k_tokens = Numeric(null=True)
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class AnalysisRun(Table, tablename="analysis_runs"):
    run_id = Varchar(primary_key=True)
    paper_id = Varchar()
    prompt_version_id = Varchar()
    profile_id = Varchar()
    model_name = Varchar()
    output_blob_path_md = Text(null=True)
    output_blob_path_json = Text(null=True)
    validation_issues_json = Text(null=True)
    error_message = Text(null=True)
    tokens_in = Integer(null=True)
    tokens_out = Integer(null=True)
    cost_usd = Numeric(null=True)
    created_at = Timestamptz(default=_now)
    started_at = Timestamptz(null=True)
    finished_at = Timestamptz(null=True)


class Job(Table, tablename="jobs"):
    job_id = Varchar(primary_key=True)
    type = Varchar()
    status = Varchar()
    paper_id = Varchar(null=True)
    run_id = Varchar(null=True)
    payload_json = Text()
    attempts = Integer()
    max_attempts = Integer()
    run_after = Timestamptz(null=True)
    last_error = Text(null=True)
    created_at = Timestamptz(default=_now)
    updated_at = Timestamptz(default=_now)


class AnalysisExtraction(Table, tablename="analysis_extractions"):
    extraction_id = Varchar(primary_key=True)
    run_id = Varchar()
    paper_id = Varchar()
    prompt_version_id = Varchar()
    entity_type = Varchar(default="paper")
    entity_ref = Varchar(null=True)
    field_path = Varchar()
    value_text = Text(null=True)
    value_numeric = Numeric(null=True)
    value_boolean = Integer(null=True)
    created_at = Timestamptz(default=_now)
