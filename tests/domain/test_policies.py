from __future__ import annotations

import pytest

from papers.domain.errors import InvalidStateTransition, NotReadyError, OutputParseFailed
from papers.domain.models import JobType, PipelineStage
from papers.domain.policies import (
    analysis_idempotency_key,
    convert_idempotency_key,
    embed_idempotency_key,
    ensure_stage_at_least,
    is_pipeline_stage_transition_allowed,
    parse_structured_json,
    pipeline_stage_rank,
    should_clear_pipeline_health,
    should_set_pipeline_health_error,
    validate_pipeline_stage_transition,
    validate_structured_output,
)


def test_pipeline_stage_ranks_monotonic() -> None:
    assert pipeline_stage_rank(PipelineStage.imported) < pipeline_stage_rank(
        PipelineStage.downloaded
    )
    assert pipeline_stage_rank(PipelineStage.downloaded) < pipeline_stage_rank(
        PipelineStage.converted
    )
    assert pipeline_stage_rank(PipelineStage.converted) < pipeline_stage_rank(
        PipelineStage.embedded
    )
    assert pipeline_stage_rank(PipelineStage.embedded) < pipeline_stage_rank(PipelineStage.analyzed)


def test_pipeline_stage_transition_rules() -> None:
    assert is_pipeline_stage_transition_allowed(PipelineStage.converted, PipelineStage.converted)
    assert is_pipeline_stage_transition_allowed(PipelineStage.converted, PipelineStage.embedded)
    assert not is_pipeline_stage_transition_allowed(PipelineStage.embedded, PipelineStage.converted)


def test_pipeline_health_rules_by_job_type() -> None:
    for job_type in (JobType.download, JobType.convert, JobType.embed):
        assert should_set_pipeline_health_error(job_type)
        assert should_clear_pipeline_health(job_type)

    for job_type in (JobType.discover, JobType.analyze):
        assert not should_set_pipeline_health_error(job_type)
        assert not should_clear_pipeline_health(job_type)


def test_pipeline_stage_transition_validation_allows_forward() -> None:
    validate_pipeline_stage_transition(PipelineStage.imported, PipelineStage.downloaded)


def test_pipeline_stage_transition_validation_rejects_regression() -> None:
    with pytest.raises(InvalidStateTransition):
        validate_pipeline_stage_transition(PipelineStage.embedded, PipelineStage.converted)


def test_idempotency_keys() -> None:
    assert (
        analysis_idempotency_key(
            paper_id="paper",
            prompt_version_id="pv1",
            profile_id="profile",
            model_name="model",
        )
        == "paper|pv1|profile|model"
    )
    assert (
        convert_idempotency_key(pdf_xxh64="abc", converter_name="docling", converter_version="1.0")
        == "abc|docling|1.0"
    )
    assert (
        embed_idempotency_key(
            md_xxh64="md",
            embedding_model="model",
            embedding_dimension=1536,
            text_slice_strategy="paragraph",
        )
        == "md|model|1536|paragraph"
    )


def test_ensure_stage_at_least_requires_minimum() -> None:
    with pytest.raises(NotReadyError):
        ensure_stage_at_least(PipelineStage.imported, PipelineStage.converted)


def test_parse_structured_json_rejects_non_object() -> None:
    with pytest.raises(OutputParseFailed):
        parse_structured_json("[1, 2, 3]")


def test_parse_structured_json_accepts_valid_object() -> None:
    """Test that valid JSON objects are parsed successfully."""
    result = parse_structured_json('{"key": "value", "count": 42}')
    assert result == {"key": "value", "count": 42}


def test_parse_structured_json_rejects_invalid_json() -> None:
    """Test that invalid JSON raises OutputParseFailed."""
    with pytest.raises(OutputParseFailed, match="not valid JSON"):
        parse_structured_json("{invalid json")


def test_ensure_stage_at_least_accepts_sufficient_stage() -> None:
    """Test that ensure_stage_at_least passes when stage is sufficient."""
    # Should not raise when current >= required
    ensure_stage_at_least(PipelineStage.converted, PipelineStage.converted)
    ensure_stage_at_least(PipelineStage.embedded, PipelineStage.converted)


def test_validate_structured_output_accepts_complete_payload() -> None:
    """Test that validate_structured_output passes when all fields present."""
    # Should not raise when all required fields are present
    validate_structured_output({"field1": "value1", "field2": "value2"}, ["field1", "field2"])
    validate_structured_output({"field1": "value1", "extra": "ok"}, ["field1"])


def test_validate_structured_output_missing_fields() -> None:
    from papers.domain.errors import OutputValidationFailed

    with pytest.raises(OutputValidationFailed):
        validate_structured_output({"ok": True}, ["required"])
