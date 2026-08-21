from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
from papers.app.use_cases.analysis import AnalyzeProjectUseCase, ExtractionFilter
from papers.app.use_cases.discovery import ImportCandidateUseCase
from papers.app.use_cases.pipeline import RunAnalysisUseCase
from papers.app.use_cases.search import FilterByExtractionsUseCase
from papers.app.use_cases.taxonomy import AttachPaperToProjectUseCase, CreateProjectUseCase
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloJobQueue,
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloProfileStore,
    PiccoloProjectStore,
    PiccoloPromptStore,
)

APPROVED = Path(__file__).resolve().parents[1] / "fixtures" / "approved"
ROLES = ("DATA-01a", "DATA-01b", "DATA-01c")


class _ImportQueue:
    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        return f"import-{paper_id}"


class _Converter:
    def pdf_to_markdown(self, pdf_path: Path) -> Any:
        raise AssertionError("analysis must not invoke conversion")

    def version(self) -> str:
        return "test"


class _Embedder:
    def model_name(self) -> str:
        return "test"

    def dimension(self) -> int:
        return 1

    def embed(self, text: str) -> list[float]:
        raise AssertionError("analysis must not invoke embedding")


class _VectorIndex:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        raise AssertionError("analysis must not update vectors")

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        raise AssertionError("analysis must not query vectors")


class _LLM:
    response: dict[str, object]

    def __init__(self) -> None:
        self.response = {}

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(self.response),
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
        )


def _load_fixtures() -> dict[str, dict[str, str]]:
    data = tomllib.loads((APPROVED / "manifest.toml").read_text(encoding="utf-8"))
    fixtures = data["fixture"]
    assert isinstance(fixtures, dict)
    return {
        role: {
            "source_paper_id": str(fixtures[role]["source_paper_id"]),
            "title": str(fixtures[role]["title"]),
            "abstract": str(fixtures[role]["abstract"]),
        }
        for role in ROLES
    }


def _harness(tmp_path: Path, name: str) -> dict[str, object]:
    db = PiccoloDatabase(tmp_path / f"{name}.sqlite")
    db.initialize_schema()
    papers = PiccoloPaperStore()
    projects = PiccoloProjectStore()
    memberships = PiccoloPaperProjectStore()
    prompts = PiccoloPromptStore()
    profiles = PiccoloProfileStore()
    runs = PiccoloAnalysisRunStore()
    jobs = PiccoloJobQueue()
    extractions = PiccoloExtractionStore()
    candidates = PiccoloCandidateStore()
    prompts.create_prompt("prompt", "Prompt")
    prompts.create_version("pv-filter", "prompt", 1, "Analyze {title}", "json_only")
    prompts.create_version("pv-target", "prompt", 2, "Analyze {title}", "json_only")
    profiles.create_profile("profile", "Local", "http://localhost")
    project_id = CreateProjectUseCase(project_store=projects)(name="alpha")
    attach = AttachPaperToProjectUseCase(
        paper_store=papers,
        project_store=projects,
        paper_project_store=memberships,
    )
    run_analysis = RunAnalysisUseCase(
        job_queue=jobs,
        prompt_store=prompts,
        profile_store=profiles,
        analysis_store=runs,
    )
    analyze = AnalyzeProjectUseCase(
        paper_project_store=memberships,
        prompt_store=prompts,
        run_analysis=run_analysis,
        filter_extractions=FilterByExtractionsUseCase(extraction_store=extractions),
    )
    llm = _LLM()
    runner = JobRunner(
        job_queue=jobs,
        context=HandlerContext(
            paper_store=papers,
            job_queue=jobs,
            blob_store=FileSystemBlobStore(tmp_path / f"{name}-blobs"),
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=llm,
            prompt_store=prompts,
            profile_store=profiles,
            analysis_store=runs,
            extraction_store=extractions,
        ),
    )
    return {
        "papers": papers,
        "candidates": candidates,
        "import_candidate": ImportCandidateUseCase(
            candidate_store=candidates,
            paper_store=papers,
            job_queue=_ImportQueue(),
        ),
        "attach": attach,
        "project_id": project_id,
        "analyze": analyze,
        "runs": runs,
        "jobs": jobs,
        "extractions": extractions,
        "run_analysis": run_analysis,
        "runner": runner,
        "llm": llm,
    }


def _import_fixture_paper(ctx: dict[str, object], role: str, candidate_id: str) -> str:
    candidates = ctx["candidates"]
    import_candidate = ctx["import_candidate"]
    assert isinstance(candidates, PiccoloCandidateStore)
    assert isinstance(import_candidate, ImportCandidateUseCase)
    row = _load_fixtures()[role]
    candidates.create_candidate(
        {
            "candidate_id": candidate_id,
            "source": "approved-fixture",
            "source_paper_id": row["source_paper_id"],
            "title": row["title"],
            "abstract": row["abstract"],
            "authors_json": "[]",
        }
    )
    return import_candidate.import_candidate(candidate_id)


def _run_successful_analysis(
    ctx: dict[str, object],
    paper_id: str,
    response: dict[str, object],
    *,
    force: bool = False,
) -> str:
    run_analysis = ctx["run_analysis"]
    runner = ctx["runner"]
    llm = ctx["llm"]
    assert isinstance(run_analysis, RunAnalysisUseCase)
    assert isinstance(runner, JobRunner)
    assert isinstance(llm, _LLM)
    llm.response = response
    run_id = run_analysis(
        paper_id=paper_id,
        prompt_id="prompt",
        prompt_version_id="pv-filter",
        profile_id="profile",
        model_name="model",
        force=force,
    )
    assert runner.run_next(datetime.now(UTC)) is True
    return run_id


def _target_run_ids(runs: PiccoloAnalysisRunStore, paper_id: str) -> set[str]:
    return {
        row["run_id"] for row in runs.list_runs(paper_id) if row["prompt_version_id"] == "pv-target"
    }


@pytest.mark.parametrize("filters", [None, []], ids=["none", "empty-list"])
def test_empty_filters_analyze_all_labeled_members(
    tmp_path: Path,
    filters: list[ExtractionFilter] | None,
) -> None:
    ctx = _harness(tmp_path, "empty-filters")
    attach = ctx["attach"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    project_id = str(ctx["project_id"])
    analyze = ctx["analyze"]
    assert isinstance(analyze, AnalyzeProjectUseCase)
    p_keep = _import_fixture_paper(ctx, "DATA-01a", "candidate-keep")
    p_other = _import_fixture_paper(ctx, "DATA-01b", "candidate-other")
    attach(paper_id=p_keep, project_id=project_id, label="primary")
    attach(paper_id=p_other, project_id=project_id, label="secondary")

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        label="primary",
        filters=filters,
    )

    assert len(run_ids) == 1
    runs = ctx["runs"]
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert _target_run_ids(runs, p_keep)
    assert not _target_run_ids(runs, p_other)


def test_one_filter_drops_non_matching_member(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "one-filter")
    attach = ctx["attach"]
    runs = ctx["runs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    p_match = _import_fixture_paper(ctx, "DATA-01a", "candidate-match")
    p_drop = _import_fixture_paper(ctx, "DATA-01b", "candidate-drop")
    attach(paper_id=p_match, project_id=project_id)
    attach(paper_id=p_drop, project_id=project_id)
    _run_successful_analysis(ctx, p_match, {"algorithm_family": "transformer"})
    _run_successful_analysis(ctx, p_drop, {"algorithm_family": "cnn"})

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        filters=[
            ExtractionFilter(
                field_path="algorithm_family",
                prompt_version_id="pv-filter",
                constraints={"value_text": "transformer"},
            )
        ],
    )

    assert len(run_ids) == 1
    assert _target_run_ids(runs, p_match)
    assert not _target_run_ids(runs, p_drop)


def test_two_filters_are_anded(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "two-filters")
    attach = ctx["attach"]
    runs = ctx["runs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    p_both = _import_fixture_paper(ctx, "DATA-01a", "candidate-both")
    p_family_only = _import_fixture_paper(ctx, "DATA-01b", "candidate-family")
    p_rating_only = _import_fixture_paper(ctx, "DATA-01c", "candidate-rating")
    for paper_id in (p_both, p_family_only, p_rating_only):
        attach(paper_id=paper_id, project_id=project_id)
    _run_successful_analysis(
        ctx,
        p_both,
        {"algorithm_family": "transformer", "rigor_class": "high"},
    )
    _run_successful_analysis(ctx, p_family_only, {"algorithm_family": "transformer"})
    _run_successful_analysis(ctx, p_rating_only, {"rigor_class": "high"})

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        filters=[
            ExtractionFilter(
                field_path="algorithm_family",
                prompt_version_id="pv-filter",
                constraints={"value_text": "transformer"},
            ),
            ExtractionFilter(
                field_path="rigor_class",
                prompt_version_id="pv-filter",
                constraints={"value_text": "high"},
            ),
        ],
    )

    assert len(run_ids) == 1
    assert _target_run_ids(runs, p_both)
    assert not _target_run_ids(runs, p_family_only)
    assert not _target_run_ids(runs, p_rating_only)


def test_latest_only_ignores_older_run(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "latest-only")
    attach = ctx["attach"]
    runs = ctx["runs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    paper_id = _import_fixture_paper(ctx, "DATA-01a", "candidate-latest")
    attach(paper_id=paper_id, project_id=project_id)
    _run_successful_analysis(ctx, paper_id, {"algorithm_family": "transformer"})
    _run_successful_analysis(ctx, paper_id, {"algorithm_family": "cnn"}, force=True)

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        filters=[
            ExtractionFilter(
                field_path="algorithm_family",
                prompt_version_id="pv-filter",
                constraints={"value_text": "transformer"},
                latest_only=True,
            )
        ],
    )

    assert run_ids == []
    assert not _target_run_ids(runs, paper_id)


def test_label_applied_before_filters(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "label-then-filter")
    attach = ctx["attach"]
    runs = ctx["runs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    p_labeled = _import_fixture_paper(ctx, "DATA-01a", "candidate-labeled")
    p_other = _import_fixture_paper(ctx, "DATA-01b", "candidate-other")
    attach(paper_id=p_labeled, project_id=project_id, label="primary")
    attach(paper_id=p_other, project_id=project_id, label="other")
    _run_successful_analysis(ctx, p_labeled, {"algorithm_family": "transformer"})
    _run_successful_analysis(ctx, p_other, {"algorithm_family": "transformer"})

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        label="primary",
        filters=[
            ExtractionFilter(
                field_path="algorithm_family",
                prompt_version_id="pv-filter",
                constraints={"value_text": "transformer"},
            )
        ],
    )

    assert len(run_ids) == 1
    assert _target_run_ids(runs, p_labeled)
    assert not _target_run_ids(runs, p_other)


def test_filter_prompt_version_may_differ_from_analyze_target(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "filter-pv")
    attach = ctx["attach"]
    runs = ctx["runs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    paper_id = _import_fixture_paper(ctx, "DATA-01a", "candidate-filter-pv")
    attach(paper_id=paper_id, project_id=project_id)
    _run_successful_analysis(ctx, paper_id, {"algorithm_family": "transformer"})

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        filters=[
            ExtractionFilter(
                field_path="algorithm_family",
                prompt_version_id="pv-filter",
                constraints={"value_text": "transformer"},
            )
        ],
    )

    assert len(run_ids) == 1
    created = [row for row in runs.list_runs(paper_id) if row["prompt_version_id"] == "pv-target"]
    assert created[0]["run_id"] == run_ids[0]


def test_unknown_constraint_raises_before_enqueue(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "unknown-key")
    attach = ctx["attach"]
    jobs = ctx["jobs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(jobs, PiccoloJobQueue)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    paper_id = _import_fixture_paper(ctx, "DATA-01a", "candidate-invalid")
    attach(paper_id=paper_id, project_id=project_id)
    before = {job["job_id"] for job in jobs.list_jobs()}

    with pytest.raises(ValueError, match="unsupported extraction constraint field"):
        analyze(
            project_id=project_id,
            prompt_version_id="pv-target",
            profile_id="profile",
            model_name="model",
            filters=[
                ExtractionFilter(
                    field_path="algorithm_family",
                    prompt_version_id="pv-filter",
                    constraints={"not_a_column": "x"},
                )
            ],
        )

    after = {job["job_id"] for job in jobs.list_jobs()}
    assert after == before


def test_empty_intersection_enqueues_nothing(tmp_path: Path) -> None:
    ctx = _harness(tmp_path, "empty-intersection")
    attach = ctx["attach"]
    runs = ctx["runs"]
    analyze = ctx["analyze"]
    assert isinstance(attach, AttachPaperToProjectUseCase)
    assert isinstance(runs, PiccoloAnalysisRunStore)
    assert isinstance(analyze, AnalyzeProjectUseCase)
    project_id = str(ctx["project_id"])
    paper_id = _import_fixture_paper(ctx, "DATA-01a", "candidate-empty")
    attach(paper_id=paper_id, project_id=project_id)
    _run_successful_analysis(ctx, paper_id, {"algorithm_family": "cnn"})

    run_ids = analyze(
        project_id=project_id,
        prompt_version_id="pv-target",
        profile_id="profile",
        model_name="model",
        filters=[
            ExtractionFilter(
                field_path="algorithm_family",
                prompt_version_id="pv-filter",
                constraints={"value_text": "transformer"},
            )
        ],
    )

    assert run_ids == []
    assert not _target_run_ids(runs, paper_id)
