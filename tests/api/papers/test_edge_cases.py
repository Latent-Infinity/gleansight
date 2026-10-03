import json

import pytest

from gleansight.api.models import OperationError
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.stores import PiccoloJobQueue
from tests.api.papers.support import call, identifier, items, prompt_version, record


def test_queued_retry_is_rejected(populated: ApiRuntime) -> None:
    # Given
    job_id = identifier(call(populated, "pipeline.embed", {"paper_id": "paper-1"}), "job_id")
    # When / Then
    with pytest.raises(OperationError, match="terminal"):
        call(populated, "jobs.retry", {"job_id": job_id})
    assert len(items(populated, "jobs.list", {})) == 1


def test_missing_retry_reports_not_found(runtime: ApiRuntime) -> None:
    # Given / When / Then
    with pytest.raises(OperationError, match="does not exist"):
        call(runtime, "jobs.retry", {"job_id": "missing"})


def test_retry_chained_conversion_preserves_source(populated: ApiRuntime) -> None:
    # Given
    previous = PiccoloJobQueue().enqueue(
        "convert",
        "paper-1",
        None,
        {"source_path": "paper.pdf", "external_ids": {"DOI": "10.123/example"}},
    )
    PiccoloJobQueue().mark_failed(previous, "Conversion failed")
    # When
    result = call(populated, "jobs.retry", {"job_id": previous})
    # Then
    stored = record(populated, "jobs.get", {"job_id": identifier(result, "job_id")})
    payload = json.loads(identifier(stored, "payload_json"))
    assert payload["source_path"] == str(populated.repo_root / "paper.pdf")
    assert payload["external_ids"] == {"DOI": "10.123/example"}


def test_download_without_source_queues_resolution(populated: ApiRuntime) -> None:
    # Given / When
    result = call(populated, "pipeline.download", {"paper_id": "paper-1"})
    # Then
    stored = record(populated, "jobs.get", {"job_id": identifier(result, "job_id")})
    assert json.loads(identifier(stored, "payload_json")) == {"max_attempts": 3}
    assert len(items(populated, "jobs.list", {"status": "queued", "paper_id": "paper-1"})) == 1
    assert items(populated, "jobs.list", {"status": "failed", "paper_id": "paper-1"}) == []


def test_bounded_runner_stops_on_empty_queue(populated: ApiRuntime, providers: None) -> None:
    # Given / When
    result = call(populated, "jobs.run-bounded", {"max_jobs": 5})
    # Then
    assert result == {"processed": 0}


def test_missing_markdown_reports_not_found(populated: ApiRuntime) -> None:
    # Given / When / Then
    with pytest.raises(OperationError, match="not available"):
        call(populated, "papers.get-markdown", {"paper_id": "paper-1"})


def test_missing_profile_prevents_provider_work(populated: ApiRuntime) -> None:
    # Given / When / Then
    with pytest.raises(OperationError, match="profile does not exist"):
        call(populated, "synthesis.ask", {"question": "Why?", "profile_id": "missing"})


def test_prompt_get_returns_structured_tags(populated: ApiRuntime) -> None:
    # Given
    prompt = identifier(
        call(populated, "prompts.create", {"name": "Methods", "tags": ["methods"]}), "prompt_id"
    )
    # When
    result = record(populated, "prompts.get", {"prompt_id": prompt})
    # Then
    assert result["tags"] == ["methods"]


def test_typed_analysis_enqueue_reuses_matching_job(populated: ApiRuntime) -> None:
    # Given
    prompt, version = prompt_version(populated)
    run = identifier(
        call(
            populated,
            "pipeline.analyze",
            {
                "paper_id": "paper-1",
                "prompt_id": prompt,
                "profile_id": "local",
                "model_name": "fake",
            },
        ),
        "run_id",
    )
    original = PiccoloJobQueue().list_jobs()[0]["job_id"]
    # When
    result = call(
        populated,
        "jobs.enqueue",
        {
            "job": {
                "type": "analyze",
                "paper_id": "paper-1",
                "run_id": run,
                "payload": {
                    "prompt_version_id": version,
                    "profile_id": "local",
                    "model_name": "fake",
                },
            }
        },
    )
    # Then
    assert result == {"job_id": original}
