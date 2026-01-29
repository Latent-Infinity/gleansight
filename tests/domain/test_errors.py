from __future__ import annotations

import pytest

from papers.domain.errors import (
    ErrorCode,
    InvalidStateTransition,
    NotReadyError,
    OutputParseFailed,
    OutputValidationFailed,
    PipelineError,
)
from papers.domain.models import PipelineStage
from papers.domain.policies import (
    ensure_stage_at_least,
    parse_structured_json,
    validate_pipeline_stage_transition,
    validate_structured_output,
)


def test_pipeline_error_exposes_code() -> None:
    err = PipelineError(ErrorCode.CONVERTER_TIMEOUT, "timeout")
    assert err.code is ErrorCode.CONVERTER_TIMEOUT
    assert str(err) == "timeout"


def test_invalid_state_transition_from_policy() -> None:
    with pytest.raises(InvalidStateTransition) as excinfo:
        validate_pipeline_stage_transition(PipelineStage.converted, PipelineStage.downloaded)

    message = str(excinfo.value)
    assert "pipeline stage cannot regress" in message
    assert "converted" in message
    assert "downloaded" in message


def test_not_ready_error_message() -> None:
    with pytest.raises(NotReadyError) as excinfo:
        ensure_stage_at_least(PipelineStage.imported, PipelineStage.embedded)

    assert "pipeline stage must be at least" in str(excinfo.value)


def test_output_validation_failed_message() -> None:
    with pytest.raises(OutputValidationFailed) as excinfo:
        validate_structured_output({"ok": True}, ["required"])

    assert "structured output missing fields" in str(excinfo.value)


def test_output_parse_failed_message() -> None:
    with pytest.raises(OutputParseFailed) as excinfo:
        parse_structured_json("{not-json}")

    assert "structured output is not valid JSON" in str(excinfo.value)
