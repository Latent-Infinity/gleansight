from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from papers.domain.errors import (
    InvalidStateTransition,
    NotReadyError,
    OutputParseFailed,
    OutputValidationFailed,
)
from papers.domain.models import JobType, OutputFormat, PipelineStage

PIPELINE_STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.imported,
    PipelineStage.downloaded,
    PipelineStage.converted,
    PipelineStage.embedded,
    PipelineStage.analyzed,
)

_PIPELINE_STAGE_RANK = {stage: index for index, stage in enumerate(PIPELINE_STAGE_ORDER)}

_PIPELINE_HEALTH_ERROR_JOB_TYPES = {
    JobType.download,
    JobType.convert,
    JobType.embed,
}


def analysis_idempotency_key(
    *,
    paper_id: str,
    prompt_version_id: str,
    profile_id: str,
    model_name: str,
) -> str:
    return "|".join([paper_id, prompt_version_id, profile_id, model_name])


def convert_idempotency_key(*, pdf_xxh64: str, converter_name: str, converter_version: str) -> str:
    return "|".join([pdf_xxh64, converter_name, converter_version])


def embed_idempotency_key(
    *,
    md_xxh64: str,
    embedding_model: str,
    embedding_dimension: int,
    text_slice_strategy: str,
) -> str:
    return "|".join([md_xxh64, embedding_model, str(embedding_dimension), text_slice_strategy])


def pipeline_stage_rank(stage: PipelineStage) -> int:
    return _PIPELINE_STAGE_RANK[stage]


def is_pipeline_stage_transition_allowed(
    current: PipelineStage,
    new: PipelineStage,
) -> bool:
    return pipeline_stage_rank(new) >= pipeline_stage_rank(current)


def validate_pipeline_stage_transition(current: PipelineStage, new: PipelineStage) -> None:
    if not is_pipeline_stage_transition_allowed(current, new):
        raise InvalidStateTransition(
            f"pipeline stage cannot regress from {current.value} to {new.value}"
        )


def should_set_pipeline_health_error(job_type: JobType) -> bool:
    return job_type in _PIPELINE_HEALTH_ERROR_JOB_TYPES


def should_clear_pipeline_health(job_type: JobType) -> bool:
    return job_type in _PIPELINE_HEALTH_ERROR_JOB_TYPES


def ensure_stage_at_least(current: PipelineStage, required: PipelineStage) -> None:
    if pipeline_stage_rank(current) < pipeline_stage_rank(required):
        raise NotReadyError(
            f"pipeline stage must be at least {required.value}, got {current.value}"
        )


def parse_structured_json(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OutputParseFailed("structured output is not valid JSON") from exc
    if not isinstance(data, dict):
        raise OutputParseFailed("structured output must be a JSON object")
    return data


def validate_structured_output(payload: dict[str, Any], required_fields: list[str]) -> None:
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise OutputValidationFailed(f"structured output missing fields: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Prompt template rendering
# ---------------------------------------------------------------------------

_TRUNCATED_RE = re.compile(r"\{markdown_truncated:(\d+)\}")


@dataclass(frozen=True)
class RenderedPrompt:
    text: str


def render_prompt_template(
    *,
    template: str,
    paper_id: str,
    title: str | None,
    abstract: str | None,
    authors: list[str],
    year: int | str | None,
    venue: str | None,
    markdown: str | None,
) -> RenderedPrompt:
    """Render a prompt template with paper metadata and markdown content."""
    text = template

    # Simple scalar placeholders (NULL → empty string)
    text = text.replace("{paper_id}", paper_id)
    text = text.replace("{title}", str(title) if title is not None else "")
    text = text.replace("{abstract}", str(abstract) if abstract is not None else "")
    text = text.replace("{authors}", ", ".join(authors))
    text = text.replace("{year}", str(year) if year is not None else "")
    text = text.replace("{venue}", str(venue) if venue is not None else "")

    # Markdown-dependent placeholders — raise NotReadyError if markdown is needed but absent
    if "{markdown}" in text:
        if markdown is None:
            raise NotReadyError("paper markdown not available for prompt template")
        text = text.replace("{markdown}", markdown)

    def _replace_truncated(match: re.Match[str]) -> str:
        if markdown is None:
            raise NotReadyError("paper markdown not available for prompt template")
        n = int(match.group(1))
        return markdown[:n]

    text = _TRUNCATED_RE.sub(_replace_truncated, text)

    return RenderedPrompt(text=text)


# ---------------------------------------------------------------------------
# LLM output parsing
# ---------------------------------------------------------------------------

_YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class ParsedOutput:
    data: dict[str, Any] | None  # None for markdown_only
    raw_text: str


def parse_llm_output(
    *,
    raw_text: str,
    output_format: OutputFormat,
) -> ParsedOutput:
    """Parse LLM response text according to the prompt's output_format."""
    if not raw_text or not raw_text.strip():
        raise OutputParseFailed("LLM returned empty response")

    if output_format is OutputFormat.markdown_only:
        return ParsedOutput(data=None, raw_text=raw_text)

    if output_format is OutputFormat.json_only:
        data = parse_structured_json(raw_text)
        return ParsedOutput(data=data, raw_text=raw_text)

    if output_format is OutputFormat.yaml_block:
        match = _YAML_FENCE_RE.search(raw_text)
        if match is None:
            raise OutputParseFailed("no fenced yaml block found in LLM output")
        import yaml  # noqa: PLC0415 — lazy import, only needed for yaml_block

        try:
            data = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise OutputParseFailed(f"invalid YAML in fenced block: {exc}") from exc
        if not isinstance(data, dict):
            raise OutputParseFailed("structured output must be a YAML object (mapping)")
        return ParsedOutput(data=data, raw_text=raw_text)

    if output_format is OutputFormat.json_block:
        match = _JSON_FENCE_RE.search(raw_text)
        if match is None:
            raise OutputParseFailed("no fenced json block found in LLM output")
        data = parse_structured_json(match.group(1))
        return ParsedOutput(data=data, raw_text=raw_text)

    raise OutputParseFailed(f"unsupported output format: {output_format}")


# ---------------------------------------------------------------------------
# Extraction flattening
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionRow:
    """Lightweight extraction row satisfying ports.Extraction protocol."""

    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: float | None
    value_boolean: int | None  # 0 or 1


@dataclass(frozen=True)
class FlattenResult:
    rows: list[ExtractionRow]
    warnings: list[dict[str, Any]]


def flatten_extractions(
    data: dict[str, Any],
    *,
    entity_type: str = "paper",
    entity_ref: str | None = None,
) -> FlattenResult:
    """Flatten nested dict/list structure into flat ExtractionRow list."""
    rows: list[ExtractionRow] = []
    warnings: list[dict[str, Any]] = []

    def _walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                _walk(child, child_path)
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                child_path = f"{path}[{idx}]"
                _walk(child, child_path)
        else:
            # Leaf value
            row = _make_leaf_row(value, path, entity_type, entity_ref)
            if row is not None:
                rows.append(row)

    def _make_leaf_row(
        value: Any,
        path: str,
        etype: str,
        eref: str | None,
    ) -> ExtractionRow | None:
        if value is None:
            return ExtractionRow(
                entity_type=etype,
                entity_ref=eref,
                field_path=path,
                value_text=None,
                value_numeric=None,
                value_boolean=None,
            )
        if isinstance(value, bool):
            return ExtractionRow(
                entity_type=etype,
                entity_ref=eref,
                field_path=path,
                value_text=None,
                value_numeric=None,
                value_boolean=1 if value else 0,
            )
        if isinstance(value, (int, float)):
            return ExtractionRow(
                entity_type=etype,
                entity_ref=eref,
                field_path=path,
                value_text=None,
                value_numeric=float(value),
                value_boolean=None,
            )
        if isinstance(value, str):
            return ExtractionRow(
                entity_type=etype,
                entity_ref=eref,
                field_path=path,
                value_text=value,
                value_numeric=None,
                value_boolean=None,
            )
        # Unexpected type at leaf — store as JSON string + warning
        warnings.append(
            {
                "path": path,
                "severity": "warning",
                "message": f"unexpected type {type(value).__name__} at leaf, stored as JSON",
                "value_preview": str(value)[:100],
            }
        )
        return ExtractionRow(
            entity_type=etype,
            entity_ref=eref,
            field_path=path,
            value_text=json.dumps(value),
            value_numeric=None,
            value_boolean=None,
        )

    _walk(data, "")
    return FlattenResult(rows=rows, warnings=warnings)


# ---------------------------------------------------------------------------
# Extraction validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    severity: str  # "error" | "warning"
    message: str
    value_preview: str | None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool  # True if no "error" severity issues
    issues: list[ValidationIssue]


def validate_extraction_output(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
) -> ValidationResult:
    """Validate parsed extraction data against a JSON Schema."""
    if schema is None:
        return ValidationResult(valid=True, issues=[])

    import jsonschema  # noqa: PLC0415

    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(data))
    if not errors:
        return ValidationResult(valid=True, issues=[])

    required_fields = set(schema.get("required", []))
    issues: list[ValidationIssue] = []

    for error in errors:
        path = _json_path(error.absolute_path)
        preview = _value_preview(error.instance)

        # Determine severity: missing required field → error, else warning
        if error.validator == "required":
            # "required" errors report which fields are missing
            for missing in error.validator_value:
                if missing not in (error.instance if isinstance(error.instance, dict) else {}):
                    issue_path = f"{path}.{missing}" if path else missing
                    issues.append(
                        ValidationIssue(
                            path=issue_path,
                            severity="error",
                            message=error.message,
                            value_preview=None,
                        )
                    )
        elif _is_required_property_error(error, required_fields):
            issues.append(
                ValidationIssue(
                    path=path,
                    severity="error",
                    message=error.message,
                    value_preview=preview,
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    path=path,
                    severity="warning",
                    message=error.message,
                    value_preview=preview,
                )
            )

    has_errors = any(i.severity == "error" for i in issues)
    return ValidationResult(valid=not has_errors, issues=issues)


def _json_path(path_deque: Any) -> str:
    """Convert jsonschema path deque to dotted string."""
    parts = list(path_deque)
    if not parts:
        return ""
    segments = []
    for part in parts:
        if isinstance(part, int):
            segments.append(f"[{part}]")
        else:
            if segments:
                segments.append(f".{part}")
            else:
                segments.append(str(part))
    return "".join(segments)


def _value_preview(value: Any) -> str | None:
    """Truncated string preview of a value."""
    if value is None:
        return None
    preview = str(value)
    return preview[:100] if len(preview) > 100 else preview


def _is_required_property_error(error: Any, root_required: set[str]) -> bool:
    """Check if a non-'required' validator error is for a required property."""
    path = list(error.absolute_path)
    if len(path) == 1 and path[0] in root_required:
        return True
    return False
