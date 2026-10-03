import pytest
from pydantic import JsonValue, ValidationError

from gleansight.api.models import OperationError
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.stores import PiccoloJobQueue
from tests.api.papers.support import call, identifier, items, prompt_version, record


@pytest.mark.parametrize(
    "job",
    [
        {"type": "download", "paper_id": "paper-1", "payload": {"source_path": "local.pdf"}},
        {"type": "convert", "paper_id": "paper-1"},
        {"type": "embed", "paper_id": "paper-1"},
        {"type": "discover", "payload": {"query": "learning", "offset": 0}},
    ],
)
def test_typed_enqueue_accepts_supported_jobs(
    populated: ApiRuntime, job: dict[str, JsonValue]
) -> None:
    # Given / When
    result = call(populated, "jobs.enqueue", {"job": job})
    # Then
    job_id = identifier(result, "job_id")
    stored = record(populated, "jobs.get", {"job_id": job_id})
    assert stored["type"] == job["type"]
    assert stored["status"] == "queued"


@pytest.mark.parametrize(
    "job",
    [
        {"type": "delete", "paper_id": "paper-1"},
        {"type": "embed", "paper_id": "paper-1", "payload": {"unknown": True}},
        {"type": "download", "paper_id": "paper-1", "payload": {"max_attempts": "3"}},
        {"type": "analyze", "paper_id": "paper-1", "payload": {}},
    ],
)
def test_invalid_job_payload_has_no_effect(runtime: ApiRuntime, job: dict[str, JsonValue]) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        call(runtime, "jobs.enqueue", {"job": job})
    assert not (runtime.repo_root / "data").exists()


def test_analysis_enqueue_validates_run_consistency(populated: ApiRuntime) -> None:
    # Given
    prompt_id, version_id = prompt_version(populated)
    result = call(
        populated,
        "pipeline.analyze",
        {
            "paper_id": "paper-1",
            "prompt_id": prompt_id,
            "profile_id": "local",
            "model_name": "fake",
        },
    )
    run_id = identifier(result, "run_id")
    job: dict[str, JsonValue] = {
        "type": "analyze",
        "paper_id": "paper-1",
        "run_id": run_id,
        "payload": {"prompt_version_id": version_id, "profile_id": "local", "model_name": "other"},
    }
    # When / Then
    with pytest.raises(OperationError, match="does not match"):
        call(populated, "jobs.enqueue", {"job": job})
    assert call(populated, "jobs.status", {}) == [{"status": "queued", "count": 1}]


def test_analysis_reuses_successful_run(populated: ApiRuntime) -> None:
    # Given
    prompt_id, _ = prompt_version(populated)
    parameters: dict[str, JsonValue] = {
        "paper_id": "paper-1",
        "prompt_id": prompt_id,
        "profile_id": "local",
        "model_name": "fake",
    }
    first = call(populated, "pipeline.analyze", parameters)
    PiccoloJobQueue().mark_succeeded(PiccoloJobQueue().list_jobs()[0]["job_id"])
    # When
    second = call(populated, "pipeline.analyze", parameters)
    # Then
    assert second == first
    assert len(items(populated, "runs.list", {})) == 1
    assert (
        record(populated, "runs.get", {"run_id": identifier(first, "run_id")})["paper_id"]
        == "paper-1"
    )


def test_project_and_scope_analysis_use_existing_usecases(populated: ApiRuntime) -> None:
    # Given
    _, version_id = prompt_version(populated)
    project_id = identifier(call(populated, "projects.create", {"name": "Project"}), "project_id")
    call(populated, "projects.attach", {"paper_id": "paper-1", "project_id": project_id})
    parameters: dict[str, JsonValue] = {
        "prompt_version_id": version_id,
        "profile_id": "local",
        "model_name": "fake",
    }
    # When
    project_runs = call(
        populated, "pipeline.analyze-project", {**parameters, "project_id": project_id}
    )
    scope_runs = call(
        populated, "pipeline.reanalyze", {**parameters, "scope": ["paper-1"], "force": True}
    )
    # Then
    assert isinstance(project_runs, list) and len(project_runs) == 1
    assert isinstance(scope_runs, list) and len(scope_runs) == 1
    assert project_runs != scope_runs


def test_bulk_cancel_deduplicates_selection(populated: ApiRuntime) -> None:
    # Given
    job_id = identifier(call(populated, "pipeline.convert", {"paper_id": "paper-1"}), "job_id")
    # When
    result = call(populated, "jobs.bulk-cancel", {"job_ids": [job_id, job_id, "missing"]})
    # Then
    assert result == {"canceled": 1}
    assert call(populated, "jobs.status", {}) == [{"status": "canceled", "count": 1}]
