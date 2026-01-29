from __future__ import annotations

import json
from typing import Any

from papers.domain.errors import (
    InvalidStateTransition,
    NotReadyError,
    OutputParseFailed,
    OutputValidationFailed,
)
from papers.domain.models import JobType, PipelineStage

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
