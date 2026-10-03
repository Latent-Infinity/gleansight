from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.domain.analysis_comparison import CohortSelection, RunInspection, RunPair
from papers.infra.piccolo.database import PiccoloDatabase


def artifact_path(run: RunInspection) -> Path:
    path = run.output_md.path
    assert path is not None
    return Path(path)


@pytest.fixture
def comparison(tmp_path: Path) -> AnalysisComparisonService:
    db = PiccoloDatabase(tmp_path / "papers.sqlite")
    db.initialize_schema()
    db.execute("INSERT INTO papers (paper_id, title) VALUES (?, ?)", ["paper-a", "Example"])
    for index, status in enumerate(("succeeded", "failed"), 1):
        run_id, prompt_id = f"run-{index}", f"prompt-{index}"
        schema = json.dumps({"properties": {f"field{index}": {"type": "string"}}})
        db.execute(
            "INSERT INTO prompt_versions (prompt_version_id, prompt_id, version, body, "
            "output_format, extraction_schema_json) VALUES (?, ?, ?, ?, ?, ?)",
            [prompt_id, "prompt", index, "Extract", "json", schema],
        )
        root = tmp_path / run_id
        root.mkdir()
        (root / "output.md").write_text(f"Output {index}\n", encoding="utf-8")
        (root / "output.json").write_text(json.dumps({"score": index}), encoding="utf-8")
        (root / "meta.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "paper_id": "paper-a",
                    "prompt": {
                        "prompt_version_id": prompt_id,
                        "extraction_schema_hash": hashlib.sha256(schema.encode()).hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )
        db.execute(
            "INSERT INTO analysis_runs (run_id, paper_id, prompt_version_id, profile_id, "
            "model_name, output_blob_path_md, output_blob_path_json, validation_issues_json, "
            "error_message, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                "paper-a",
                prompt_id,
                "profile",
                "model",
                str(root / "output.md"),
                str(root / "output.json"),
                json.dumps([{"message": "schema rejected"}]) if index == 2 else None,
                "validation failed" if index == 2 else None,
                10,
                20,
            ],
        )
        db.execute(
            "INSERT INTO jobs (job_id, type, status, paper_id, "
            "run_id, payload_json, attempts, max_attempts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [f"job-{index}", "analyze", status, "paper-a", run_id, "{}", 0, 1],
        )
        for field, value in [("score", str(index)), (f"only{index}", "x")]:
            db.execute(
                "INSERT INTO analysis_extractions (extraction_id, run_id, paper_id, "
                "prompt_version_id, entity_type, field_path, value_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [f"{run_id}-{field}", run_id, "paper-a", prompt_id, "paper", field, value],
            )
    db.execute("UPDATE analysis_runs SET cost_usd = NULL")
    return AnalysisComparisonService(db)


def test_compare_failed_run_distinguishes_absence_schema_and_unknown_cost(
    comparison: AnalysisComparisonService,
) -> None:
    # Given two stored outputs with different schemas and extraction sets.
    before = comparison.database.fetchall("SELECT * FROM analysis_runs ORDER BY run_id")
    source_hashes = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in comparison.database.path.parent.glob("run-*/*")
    }

    # When the exact runs are compared.
    result = comparison.compare(RunPair(baseline_run_id="run-1", revised_run_id="run-2"))
    # Then failures and missing values remain explicit, and the source rows are immutable.
    assert result.schema_changed
    assert result.baseline.output_md.text == "Output 1\n"
    assert result.revised.status == "failed"
    assert result.revised.validation_issues == [{"message": "schema rejected"}]
    assert result.revised.cost_status == "unknown"
    assert result.revised.cost_usd is None
    assert "-Output 1" in result.output_diff
    assert {x.field_path: x.change for x in result.extraction_diff} == {
        "only1": "missing_revised",
        "only2": "missing_baseline",
        "score": "changed",
    }
    assert comparison.database.fetchall("SELECT * FROM analysis_runs ORDER BY run_id") == before
    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_hashes
    } == source_hashes


def test_missing_output_is_visible(comparison: AnalysisComparisonService) -> None:
    # Given a deleted output.
    artifact_path(comparison.inspect("run-2")).unlink()
    # When it is opened.
    result = comparison.inspect("run-2")
    # Then no fabricated output replaces it.
    assert result.output_md.state == "unavailable"
    assert result.output_md.error
    assert result.output_md.text is None


def test_metadata_mismatch_is_visible(comparison: AnalysisComparisonService) -> None:
    # Given an output whose metadata belongs to another run.
    path = artifact_path(comparison.inspect("run-1")).parent / "meta.json"
    path.write_text(
        '{"run_id":"other","paper_id":"paper-a","prompt":{"prompt_version_id":"prompt-1"}}'
    )
    # When inspected.
    result = comparison.inspect("run-1")
    # Then the output is unavailable with an identity error.
    assert result.output_md.state == "unavailable"
    assert "identity" in (result.output_md.error or "")


def test_compare_rejects_cross_paper(comparison: AnalysisComparisonService) -> None:
    # Given a run belonging to a different paper.
    comparison.database.execute(
        "UPDATE analysis_runs SET paper_id = ? WHERE run_id = ?", ["paper-b", "run-2"]
    )
    # When compared, then the paper identity guard refuses it.
    with pytest.raises(ValueError, match="same paper"):
        comparison.compare(RunPair(baseline_run_id="run-1", revised_run_id="run-2"))


def test_saved_cohort_survives_restart_and_detects_changed_output(
    comparison: AnalysisComparisonService,
) -> None:
    # Given an explicit baseline and revision cohort.
    selection = CohortSelection(
        name="Revision check",
        baseline_prompt_version_id="prompt-1",
        revised_prompt_version_id="prompt-2",
        pairs=(RunPair(baseline_run_id="run-1", revised_run_id="run-2"),),
    )
    saved = comparison.save_cohort(selection)
    restarted = AnalysisComparisonService(PiccoloDatabase(comparison.database.path))
    # When reopened by a fresh service.
    report = restarted.compare_cohort(saved.cohort_id)
    # Then the exact run selection survives and later mutations fail verification.
    assert report.cohort == saved
    assert len(report.comparisons) == 1
    artifact_path(report.comparisons[0].baseline).write_text("Changed baseline")
    with pytest.raises(ValueError, match="changed"):
        restarted.compare_cohort(saved.cohort_id)
