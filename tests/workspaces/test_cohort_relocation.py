from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from pydantic import TypeAdapter

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure, Success
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.domain.analysis_comparison import CohortReport, SavedCohort
from tests.app.use_cases.test_analysis_comparison import comparison as comparison
from tests.app.use_cases.test_analysis_comparison_edges import selection


def test_public_cohort_survives_authorized_workspace_relocation(
    comparison: AnalysisComparisonService, tmp_path: Path
) -> None:
    for run_id in ("run-1", "run-2"):
        target = tmp_path / "data/blobs/analysis" / run_id
        shutil.copytree(tmp_path / run_id, target)
        comparison.database.execute(
            "UPDATE analysis_runs SET output_blob_path_md=?, output_blob_path_json=? "
            "WHERE run_id=?",
            [str(target / "output.md"), str(target / "output.json"), run_id],
        )
    config = tmp_path / "comparison.toml"
    config.write_text(f'[data]\ndb_path = "{comparison.database.path}"\n')
    client = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path, config_path=config, allow_approvals=True)
    )
    saved = client.call(
        "papers.analysis.cohorts.save", {"selection": selection().model_dump(mode="json")}
    )
    assert isinstance(saved, Success), saved
    cohort = SavedCohort.model_validate(saved.data)
    original_record = comparison.database.fetchone(
        "SELECT document_json FROM analysis_evaluation_cohorts WHERE cohort_id=?",
        [cohort.cohort_id],
    )
    original_files = {
        str(path.relative_to(tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / "data/blobs/analysis").rglob("*")
        if path.is_file()
    }
    backed_up = client.call("workspaces.backup", {})
    assert isinstance(backed_up, Success), backed_up
    backup = TypeAdapter(dict[str, str]).validate_python(backed_up.data)
    destination = tmp_path / "restored-workspace"
    restored = client.call(
        "workspaces.restore",
        {"backup_path": backup["backup_path"], "destination": str(destination)},
    )
    assert isinstance(restored, Success), restored
    restored_fields = TypeAdapter(dict[str, str]).validate_python(restored.data)
    restored_config = ApiConfiguration(
        repo_root=destination, config_path=Path(restored_fields["config_path"])
    )
    restored_database = ApiRuntime(restored_config).paper_database
    assert (
        restored_database.fetchone(
            "SELECT document_json FROM analysis_evaluation_cohorts WHERE cohort_id=?",
            [cohort.cohort_id],
        )
        == original_record
    )
    assert {
        name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
        for name in original_files
    } == original_files
    result = GleansightAPI(restored_config).call(
        "papers.analysis.cohorts.compare", {"cohort_id": cohort.cohort_id}
    )
    assert isinstance(result, Success), result
    report = CohortReport.model_validate(result.data)
    assert report.cohort == cohort
    assert report.comparisons[0].baseline.output_md.path == str(
        destination / "data/blobs/analysis/run-1/output.md"
    )
    assert report.comparisons[0].baseline.output_md.text == "Output 1\n"
    assert report.comparisons[0].revised.status == "failed"
    assert (
        comparison.database.fetchone(
            "SELECT document_json FROM analysis_evaluation_cohorts WHERE cohort_id=?",
            [cohort.cohort_id],
        )
        == original_record
    )
    (tmp_path / "restored-cohort-result.json").write_text(result.model_dump_json(indent=2))
    metadata = destination / "data/blobs/analysis/run-1/meta.json"
    metadata.write_text(metadata.read_text() + "\n")
    stale = GleansightAPI(restored_config).call(
        "papers.analysis.cohorts.compare", {"cohort_id": cohort.cohort_id}
    )
    assert isinstance(stale, Failure) and "source has changed" in stale.error.message
    assert isinstance(
        client.call("papers.analysis.cohorts.compare", {"cohort_id": cohort.cohort_id}), Success
    )
    assert {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in original_files
    } == original_files
    (tmp_path / "restored-cohort-stale-metadata.json").write_text(stale.model_dump_json(indent=2))
