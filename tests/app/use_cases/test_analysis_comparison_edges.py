from __future__ import annotations

import json

import pytest

from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.app.use_cases.analysis_comparison_artifacts import MAX_ARTIFACT_BYTES
from papers.domain.analysis_comparison import CohortSelection, RunPair
from papers.domain.errors import NotFoundError
from papers.infra.analysis_cohorts import AnalysisCohortStore
from tests.app.use_cases.test_analysis_comparison import artifact_path
from tests.app.use_cases.test_analysis_comparison import comparison as comparison


def selection() -> CohortSelection:
    return CohortSelection(
        name="Cohort",
        baseline_prompt_version_id="prompt-1",
        revised_prompt_version_id="prompt-2",
        pairs=(RunPair(baseline_run_id="run-1", revised_run_id="run-2"),),
    )


@pytest.mark.parametrize(
    "mutation", ["empty", "missing_metadata", "large", "invalid_json", "schema", "source", "path"]
)
def test_artifact_boundary_reports_exact_state(
    comparison: AnalysisComparisonService, mutation: str
) -> None:
    # Given a stored run with one boundary condition.
    output = artifact_path(comparison.inspect("run-1"))
    metadata = output.parent / "meta.json"
    expected = "unavailable"
    if mutation == "empty":
        output.write_text("")
        expected = "empty"
    elif mutation == "missing_metadata":
        metadata.unlink()
    elif mutation == "large":
        output.write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))
    elif mutation == "invalid_json":
        (output.parent / "output.json").write_text("{invalid")
    elif mutation == "schema":
        comparison.database.execute(
            "UPDATE prompt_versions SET extraction_schema_json = ? WHERE prompt_version_id = ?",
            ["{}", "prompt-1"],
        )
    elif mutation == "source":
        document = json.loads(metadata.read_text())
        document["input_provenance"] = {"md_fingerprint_xxh64": "old"}
        metadata.write_text(json.dumps(document))
        comparison.database.execute("UPDATE papers SET md_fingerprint_xxh64 = ?", ["new"])
    elif mutation == "path":
        comparison.database.execute(
            "UPDATE analysis_runs SET output_blob_path_md = ? WHERE run_id = ?",
            [str(output.parent / "wrong.md"), "run-1"],
        )
    # When inspected.
    result = comparison.inspect("run-1")
    # Then the boundary is visible without empty-string substitution.
    artifact = result.output_json if mutation == "invalid_json" else result.output_md
    assert artifact.state == expected
    assert artifact.text == "" if mutation == "empty" else artifact.error


def test_absent_outputs_have_no_diff(comparison: AnalysisComparisonService) -> None:
    # Given a run which never produced an output.
    comparison.database.execute(
        "UPDATE analysis_runs SET output_blob_path_md = NULL WHERE run_id = ?", ["run-2"]
    )
    # When compared.
    result = comparison.compare(RunPair(baseline_run_id="run-1", revised_run_id="run-2"))
    # Then missing output cannot look like an intentional empty document.
    assert result.revised.output_md.state == "absent"
    assert "unavailable" in result.output_diff.lower()


@pytest.mark.parametrize("complete", [True, False])
def test_cost_requires_provider_usage_and_pricing(
    comparison: AnalysisComparisonService, complete: bool
) -> None:
    # Given a database amount, including potentially defaulted zero, and metadata.
    path = artifact_path(comparison.inspect("run-1")).parent / "meta.json"
    metadata = json.loads(path.read_text())
    metadata["usage"] = {"tokens_in": 10, "tokens_out": 20, "cost_usd": 0.25}
    metadata["endpoint"] = (
        {"pricing": {"input_price_per_1k_tokens": 5, "output_price_per_1k_tokens": 10}}
        if complete
        else {}
    )
    path.write_text(json.dumps(metadata))
    comparison.database.execute(
        "UPDATE analysis_runs SET cost_usd = ? WHERE run_id = ?", [0.25, "run-1"]
    )
    # When inspected.
    result = comparison.inspect("run-1")
    # Then cost is recorded only with both usage and pricing.
    assert result.cost_usd == (0.25 if complete else None)
    assert result.cost_status == ("recorded" if complete else "unknown")


@pytest.mark.parametrize(
    "change, expected",
    [
        ("same_prompt", "distinct prompt"),
        ("wrong_prompt", "match"),
        ("baseline_failed", "successful baseline"),
        ("revision_queued", "completed"),
        ("duplicate", "exactly one"),
        ("project", "outside"),
        ("stale", "unavailable"),
    ],
)
def test_cohort_refuses_ambiguous_or_unavailable_inputs(
    comparison: AnalysisComparisonService, change: str, expected: str
) -> None:
    # Given an invalid selection or run state.
    request = selection()
    if change == "same_prompt":
        request = request.model_copy(update={"revised_prompt_version_id": "prompt-1"})
    elif change == "wrong_prompt":
        request = request.model_copy(update={"revised_prompt_version_id": "wrong"})
    elif change == "baseline_failed":
        comparison.database.execute("UPDATE jobs SET status = 'failed' WHERE run_id = 'run-1'")
    elif change == "revision_queued":
        comparison.database.execute("UPDATE jobs SET status = 'queued' WHERE run_id = 'run-2'")
    elif change == "duplicate":
        request = request.model_copy(update={"pairs": request.pairs * 2})
    elif change == "project":
        request = request.model_copy(update={"project_id": "outside"})
    elif change == "stale":
        artifact_path(comparison.inspect("run-1")).unlink()
    # When saving, then no invalid cohort is persisted.
    with pytest.raises(ValueError, match=expected):
        comparison.save_cohort(request)
    assert AnalysisCohortStore(comparison.database).list() == ()


def test_saved_project_cohort_lists_after_restart(comparison: AnalysisComparisonService) -> None:
    # Given selected paper membership and a saved cohort.
    comparison.database.execute(
        "INSERT INTO paper_projects (paper_id, project_id) VALUES (?, ?)", ["paper-a", "project"]
    )
    saved = comparison.save_cohort(selection().model_copy(update={"project_id": "project"}))
    # When listing through a new store.
    listed = AnalysisCohortStore(comparison.database).list()
    # Then the project and run choices remain exact.
    assert listed == (saved,)
    assert listed[0].selection.project_id == "project"


def test_missing_records_report_not_found(comparison: AnalysisComparisonService) -> None:
    # Given no matching run or saved cohort.
    # When querying, then callers receive the established not-found error.
    with pytest.raises(NotFoundError):
        comparison.inspect("missing")
    with pytest.raises(NotFoundError):
        AnalysisCohortStore(comparison.database).get("missing")


def test_same_run_pair_and_empty_cohort_are_invalid() -> None:
    # Given invalid selections, when parsed then the boundary rejects them.
    with pytest.raises(ValueError, match="distinct"):
        RunPair(baseline_run_id="same", revised_run_id="same")
    with pytest.raises(ValueError):
        CohortSelection(
            name="Empty",
            baseline_prompt_version_id="old",
            revised_prompt_version_id="new",
            pairs=(),
        )


def test_successful_baseline_requires_stored_output(comparison: AnalysisComparisonService) -> None:
    # Given a successful run with a missing recorded artifact.
    comparison.database.execute(
        "UPDATE analysis_runs SET output_blob_path_md = NULL WHERE run_id = 'run-1'"
    )
    # When saved, then the baseline cannot be silently accepted without output.
    with pytest.raises(ValueError, match="without its stored output"):
        comparison.save_cohort(selection())
