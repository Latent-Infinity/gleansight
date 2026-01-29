from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from papers.domain import models


def _now() -> datetime:
    return datetime.now(UTC)


def test_paper_requires_title_and_stage() -> None:
    with pytest.raises(ValueError):
        models.Paper(
            paper_id="01H",
            title="",
            pipeline_stage=models.PipelineStage.imported,
            pipeline_health=models.PipelineHealth.ok,
            created_at=_now(),
            updated_at=_now(),
        )

    paper = models.Paper(
        paper_id="01H",
        title="Paper",
        pipeline_stage=models.PipelineStage.imported,
        pipeline_health=models.PipelineHealth.ok,
        created_at=_now(),
        updated_at=_now(),
    )
    assert paper.title == "Paper"

    with pytest.raises(ValidationError):
        models.Paper(
            paper_id="01H",
            title="Paper",
            pipeline_stage="invalid",  # type: ignore[arg-type]
            pipeline_health=models.PipelineHealth.ok,
            created_at=_now(),
            updated_at=_now(),
        )
    with pytest.raises(ValidationError):
        models.Paper(
            paper_id="01H",
            title="Paper",
            pipeline_stage=models.PipelineStage.imported,
            pipeline_health=None,  # type: ignore[arg-type]
            created_at=_now(),
            updated_at=_now(),
        )


def test_candidate_requires_title() -> None:
    with pytest.raises(ValueError):
        models.Candidate(
            candidate_id="cand",
            source="source",
            source_paper_id="spid",
            title=" ",
            created_at=_now(),
            updated_at=_now(),
        )

    candidate = models.Candidate(
        candidate_id="cand",
        source="source",
        source_paper_id="spid",
        title="Title",
        created_at=_now(),
        updated_at=_now(),
    )
    assert candidate.title == "Title"

    with pytest.raises(ValidationError):
        models.Candidate(
            candidate_id="cand",
            source=None,  # type: ignore[arg-type]
            source_paper_id="spid",
            title="Title",
            created_at=_now(),
            updated_at=_now(),
        )


def test_project_requires_name() -> None:
    with pytest.raises(ValueError):
        models.Project(
            project_id="proj",
            name=None,  # type: ignore[arg-type]
            created_at=_now(),
            updated_at=_now(),
        )

    project = models.Project(
        project_id="proj",
        name="Project",
        created_at=_now(),
        updated_at=_now(),
    )
    assert project.name == "Project"


def test_prompt_version_markdown_only_rejects_schema() -> None:
    with pytest.raises(ValueError):
        models.PromptVersion(
            prompt_version_id="01H",
            prompt_id="01H",
            version=1,
            body="body",
            output_format=models.OutputFormat.markdown_only,
            extraction_schema_json={"type": "object"},
            created_at=_now(),
        )


def test_prompt_version_allows_schema_for_structured_formats() -> None:
    version = models.PromptVersion(
        prompt_version_id="01H",
        prompt_id="01H",
        version=1,
        body="body",
        output_format=models.OutputFormat.json_only,
        extraction_schema_json={"type": "object"},
        created_at=_now(),
    )
    assert version.extraction_schema_json == {"type": "object"}


def test_prompt_model_requires_name() -> None:
    with pytest.raises(ValidationError):
        models.Prompt(
            prompt_id="prompt",
            name=None,  # type: ignore[arg-type]
            created_at=_now(),
            updated_at=_now(),
        )

    prompt = models.Prompt(
        prompt_id="prompt",
        name="My Prompt",
        description="desc",
        domain="domain",
        tags=["tag-a", "tag-b"],
        created_at=_now(),
        updated_at=_now(),
    )
    assert prompt.name == "My Prompt"
    assert prompt.tags == ["tag-a", "tag-b"]


def test_prompt_version_requires_body() -> None:
    with pytest.raises(ValidationError):
        models.PromptVersion(
            prompt_version_id="01H",
            prompt_id="01H",
            version=1,
            body=None,  # type: ignore[arg-type]
            output_format=models.OutputFormat.json_only,
            created_at=_now(),
        )

    with pytest.raises(ValidationError):
        models.PromptVersion(
            prompt_version_id="01H",
            prompt_id="01H",
            version=1,
            body="body",
            output_format="invalid",  # type: ignore[arg-type]
            created_at=_now(),
        )


def test_job_requires_run_id_for_analyze() -> None:
    with pytest.raises(ValueError):
        models.JobRecord(
            job_id="01H",
            type=models.JobType.analyze,
            status=models.JobStatus.queued,
            paper_id="paper",
            run_id=None,
            payload={"x": 1},
            attempts=0,
            max_attempts=3,
            run_after=None,
            created_at=_now(),
            updated_at=_now(),
        )


def test_tag_type_validation() -> None:
    tag = models.Tag(
        tag_id="01H",
        name="method",
        type=models.TagType.method,
        created_at=_now(),
        updated_at=_now(),
    )
    assert tag.type is models.TagType.method


def test_tag_requires_name_and_type() -> None:
    with pytest.raises(ValidationError):
        models.Tag(
            tag_id="01H",
            name=None,  # type: ignore[arg-type]
            type=models.TagType.subject,
            created_at=_now(),
            updated_at=_now(),
        )

    with pytest.raises(ValidationError):
        models.Tag(
            tag_id="01H",
            name="tag",
            type="invalid",  # type: ignore[arg-type]
            created_at=_now(),
            updated_at=_now(),
        )


def test_endpoint_profile_requires_base_url() -> None:
    with pytest.raises(ValueError):
        models.EndpointProfile(
            profile_id="01H",
            name="local",
            base_url="",
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )

    profile = models.EndpointProfile(
        profile_id="01H",
        name="local",
        base_url="http://localhost",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    assert profile.base_url == "http://localhost"


def test_analysis_run_requires_core_fields() -> None:
    with pytest.raises(ValueError):
        models.AnalysisRun(
            run_id="run",
            paper_id="paper",
            prompt_version_id="prompt",
            profile_id="profile",
            model_name=None,  # type: ignore[arg-type]
            created_at=_now(),
        )

    run = models.AnalysisRun(
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        profile_id="profile",
        model_name="model",
        created_at=_now(),
    )
    assert run.model_name == "model"


def test_job_allows_analyze_with_run_id() -> None:
    job = models.JobRecord(
        job_id="job",
        type=models.JobType.analyze,
        status=models.JobStatus.queued,
        paper_id="paper",
        run_id="run",
        payload={"x": 1},
        attempts=0,
        max_attempts=3,
        run_after=None,
        created_at=_now(),
        updated_at=_now(),
    )
    assert job.run_id == "run"


def test_job_requires_enums() -> None:
    with pytest.raises(ValidationError):
        models.JobRecord(
            job_id="job",
            type="invalid",  # type: ignore[arg-type]
            status=models.JobStatus.queued,
            paper_id="paper",
            run_id="run",
            payload={"x": 1},
            attempts=0,
            max_attempts=3,
            run_after=None,
            created_at=_now(),
            updated_at=_now(),
        )

    with pytest.raises(ValidationError):
        models.JobRecord(
            job_id="job",
            type=models.JobType.download,
            status="invalid",  # type: ignore[arg-type]
            paper_id="paper",
            run_id=None,
            payload={"x": 1},
            attempts=0,
            max_attempts=3,
            run_after=None,
            created_at=_now(),
            updated_at=_now(),
        )


def test_extraction_requires_field_path() -> None:
    with pytest.raises(ValueError):
        models.Extraction(
            extraction_id="ext",
            run_id="run",
            paper_id="paper",
            prompt_version_id="prompt",
            field_path=None,  # type: ignore[arg-type]
            created_at=_now(),
        )

    extraction = models.Extraction(
        extraction_id="ext",
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        field_path="paper.title",
        created_at=_now(),
    )
    assert extraction.field_path == "paper.title"
