import json

import pytest
from pydantic import JsonValue, ValidationError

from gleansight.api.models import OperationError
from gleansight.api.runtime import ApiRuntime
from papers.domain.errors import InvalidExtractionSchemaError, NotFoundError
from papers.infra.piccolo.stores import PiccoloCandidateStore
from tests.api.papers.support import call, identifier, items, prompt_version, record


def candidate(runtime: ApiRuntime) -> None:
    runtime.paper_database.bind_tables()
    PiccoloCandidateStore().create_candidate(
        {
            "candidate_id": "candidate-1",
            "source": "semantic_scholar",
            "source_paper_id": "s2-1",
            "title": "Learning methods",
            "external_ids_json": json.dumps({"DOI": "10.123/example"}),
        }
    )


def test_import_is_atomic_with_memberships(runtime: ApiRuntime) -> None:
    # Given
    candidate(runtime)
    project = identifier(call(runtime, "projects.create", {"name": "Methods"}), "project_id")
    tag = identifier(
        call(runtime, "tags.create", {"name": "Learning", "tag_type": "method"}), "tag_id"
    )
    # When
    result = call(
        runtime,
        "candidates.import",
        {"candidate_id": "candidate-1", "project_ids": [project], "tag_ids": [tag]},
    )
    # Then
    paper_id = identifier(result, "paper_id")
    assert items(runtime, "projects.members", {"project_id": project})[0]["paper_id"] == paper_id
    assert items(runtime, "tags.members", {"tag_id": tag})[0]["paper_id"] == paper_id
    assert call(runtime, "jobs.status", {}) == [{"status": "queued", "count": 1}]


def test_import_reuses_paper_and_download(runtime: ApiRuntime) -> None:
    # Given
    candidate(runtime)
    first = call(runtime, "candidates.import", {"candidate_id": "candidate-1"})
    # When
    second = call(runtime, "candidates.import", {"candidate_id": "candidate-1"})
    # Then
    assert second == first
    assert call(runtime, "jobs.status", {}) == [{"status": "queued", "count": 1}]


def test_unknown_membership_does_not_import(runtime: ApiRuntime) -> None:
    # Given
    candidate(runtime)
    # When / Then
    with pytest.raises(NotFoundError):
        call(
            runtime,
            "candidates.import",
            {"candidate_id": "candidate-1", "project_ids": ["missing"]},
        )
    assert call(runtime, "papers.list", {}) == {"items": [], "next_offset": None}
    assert call(runtime, "jobs.status", {}) == []


def test_reject_prevents_import(runtime: ApiRuntime) -> None:
    # Given
    candidate(runtime)
    call(runtime, "candidates.reject", {"candidate_id": "candidate-1"})
    # When / Then
    with pytest.raises(ValueError):
        call(runtime, "candidates.import", {"candidate_id": "candidate-1"})
    assert len(items(runtime, "candidates.list", {"status": "rejected"})) == 1


def test_prompt_versions_increment_without_mutation(populated: ApiRuntime) -> None:
    # Given
    prompt_id, previous = prompt_version(populated)
    # When
    result = record(
        populated,
        "prompts.create-version",
        {
            "prompt_id": prompt_id,
            "body": "Updated",
            "output_format": "json_only",
            "extraction_schema_json": {"type": "object"},
        },
    )
    # Then
    assert result["version"] == 2
    assert record(populated, "prompts.get-version", {"prompt_version_id": previous})["version"] == 1
    assert len(items(populated, "prompts.versions", {"prompt_id": prompt_id})) == 2


def test_prompt_schema_rejection_writes_no_version(populated: ApiRuntime) -> None:
    # Given
    prompt_id, _ = prompt_version(populated)
    # When / Then
    with pytest.raises(InvalidExtractionSchemaError):
        call(
            populated,
            "prompts.create-version",
            {
                "prompt_id": prompt_id,
                "body": "Updated",
                "output_format": "json_only",
                "extraction_schema_json": {"type": "unknown"},
            },
        )
    assert len(items(populated, "prompts.versions", {"prompt_id": prompt_id})) == 1


def test_pipeline_enqueue_deduplicates(populated: ApiRuntime) -> None:
    # Given
    first = call(populated, "pipeline.convert", {"paper_id": "paper-1"})
    # When
    second = call(populated, "pipeline.convert", {"paper_id": "paper-1"})
    # Then
    assert second == first
    assert call(populated, "jobs.status", {}) == [{"status": "queued", "count": 1}]


def test_unknown_paper_cannot_enqueue(runtime: ApiRuntime) -> None:
    # Given / When / Then
    with pytest.raises(OperationError, match="does not exist"):
        call(runtime, "pipeline.embed", {"paper_id": "missing"})
    assert call(runtime, "jobs.status", {}) == []


@pytest.mark.parametrize(
    "parameters",
    [
        {"paper_id": "x", "max_attempts": "3"},
        {"paper_id": "x", "force": True},
        {"paper_id": "x", "max_attempts": 0},
    ],
)
def test_pipeline_invalid_input_has_no_effect(
    runtime: ApiRuntime, parameters: dict[str, JsonValue]
) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        call(runtime, "pipeline.convert", parameters)
    assert not (runtime.repo_root / "data").exists()
