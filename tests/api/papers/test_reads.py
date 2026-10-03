import pytest
from pydantic import JsonValue

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure, OperationError
from gleansight.api.runtime import ApiRuntime
from tests.api.papers.support import call, identifier, items, prompt_version, record


@pytest.mark.parametrize(
    "operation",
    [
        "candidates.list",
        "papers.list",
        "runs.list",
        "jobs.list",
        "prompts.list",
        "projects.list",
        "tags.list",
        "profiles.list",
    ],
)
def test_empty_lists_are_pageable_without_providers(
    runtime: ApiRuntime, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    def forbid_providers(self: ApiRuntime) -> None:
        pytest.fail("Read initialized external providers")

    monkeypatch.setattr(ApiRuntime, "papers", property(forbid_providers))
    # When
    result = call(runtime, operation, {"limit": 1, "offset": 0})
    # Then
    assert result == {"items": [], "next_offset": None}


@pytest.mark.parametrize(
    "operation,parameters",
    [
        ("candidates.get", {"candidate_id": "missing"}),
        ("papers.get", {"paper_id": "missing"}),
        ("runs.get", {"run_id": "missing"}),
        ("jobs.get", {"job_id": "missing"}),
        ("prompts.get", {"prompt_id": "missing"}),
        ("projects.get", {"project_id": "missing"}),
        ("tags.get", {"tag_id": "missing"}),
        ("profiles.get", {"profile_id": "missing"}),
    ],
)
def test_missing_record_reports_stable_error(
    api: GleansightAPI, operation: str, parameters: dict[str, JsonValue]
) -> None:
    # Given / When
    result = api.call(f"papers.{operation}", parameters)
    # Then
    assert isinstance(result, Failure)
    assert result.error.code == "not_found"


def test_profile_inspection_excludes_url_credentials(populated: ApiRuntime) -> None:
    # Given
    populated.paper_database.execute(
        "UPDATE endpoint_profiles SET base_url = ? WHERE profile_id = ?",
        ["https://user:secret@example.test?api_key=secret", "local"],
    )
    # When
    result = record(populated, "profiles.get", {"profile_id": "local"})
    # Then
    assert result["profile_id"] == "local"
    assert "base_url" not in result and "api_key" not in result
    assert "secret" not in str(result)


def test_membership_attachments_are_idempotent(populated: ApiRuntime) -> None:
    # Given
    project_id = identifier(call(populated, "projects.create", {"name": "Project"}), "project_id")
    tag_id = identifier(
        call(populated, "tags.create", {"name": "Tag", "tag_type": "custom"}), "tag_id"
    )
    call(
        populated,
        "projects.attach",
        {"project_id": project_id, "paper_id": "paper-1", "label": "primary"},
    )
    call(populated, "tags.attach", {"tag_id": tag_id, "paper_id": "paper-1", "confidence": 0.7})
    # When
    call(populated, "projects.attach", {"project_id": project_id, "paper_id": "paper-1"})
    call(populated, "tags.attach", {"tag_id": tag_id, "paper_id": "paper-1"})
    # Then
    assert len(items(populated, "projects.for-paper", {"paper_id": "paper-1"})) == 1
    assert len(items(populated, "tags.for-paper", {"paper_id": "paper-1"})) == 1
    assert (
        len(items(populated, "projects.members", {"project_id": project_id, "label": "primary"}))
        == 1
    )
    assert record(populated, "projects.get", {"project_id": project_id})["name"] == "Project"
    assert record(populated, "tags.get", {"tag_id": tag_id})["name"] == "Tag"


def test_reset_changes_stage(populated: ApiRuntime) -> None:
    # Given / When
    call(populated, "papers.reset-stage", {"paper_id": "paper-1", "stage": "converted"})
    # Then
    assert len(items(populated, "papers.list", {"stage": "converted"})) == 1
    assert items(populated, "papers.list", {"stage": "imported"}) == []


def test_delete_cascades_and_unlinks_candidate(populated: ApiRuntime) -> None:
    # Given
    call(populated, "pipeline.convert", {"paper_id": "paper-1"})
    # When
    call(populated, "papers.delete", {"paper_id": "paper-1"})
    # Then
    assert items(populated, "papers.list", {}) == []
    assert call(populated, "jobs.status", {}) == []


def test_markdown_path_cannot_escape_blobs(populated: ApiRuntime) -> None:
    # Given
    from papers.infra.piccolo.stores import PiccoloPaperStore

    PiccoloPaperStore().create_paper({"paper_id": "../../secret", "title": "Hostile ID"})
    # When / Then
    with pytest.raises(OperationError, match="inside"):
        call(populated, "papers.get-markdown", {"paper_id": "../../secret"})


def test_filter_and_aggregates_read_real_extractions(populated: ApiRuntime) -> None:
    # Given
    _, version_id = prompt_version(populated)
    populated.paper_database.execute(
        "INSERT INTO analysis_extractions (extraction_id, paper_id, run_id, prompt_version_id, "
        "entity_type, field_path, value_text, value_numeric, value_boolean) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["e1", "paper-1", "r1", version_id, "paper", "score", "high", 4.5, 1],
    )
    params: dict[str, JsonValue] = {
        "field_path": "score",
        "prompt_version_id": version_id,
        "latest_only": False,
    }
    # When
    result = call(populated, "query.filter", {**params, "constraints": {"value_boolean": True}})
    # Then
    assert result == ["paper-1"]
    assert call(populated, "query.count", params) == {"high": 1}
    assert call(populated, "query.average", params) == 4.5
    assert call(populated, "query.average", {**params, "group_by": "value_text"}) == {"high": 4.5}
    assert (
        len(
            items(
                populated,
                "runs.extractions",
                {"paper_id": "paper-1", "prompt_version_id": version_id},
            )
        )
        == 1
    )
    assert len(items(populated, "runs.extractions", {"paper_id": "paper-1"})) == 1
