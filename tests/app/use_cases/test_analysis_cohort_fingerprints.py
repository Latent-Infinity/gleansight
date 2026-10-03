from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Success
from gleansight.api.runtime import ApiConfiguration
from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.domain.analysis_comparison import PinnedComparison, SavedCohort
from papers.infra.analysis_cohorts import AnalysisCohortStore
from tests.app.use_cases.test_analysis_comparison import artifact_path
from tests.app.use_cases.test_analysis_comparison import comparison as comparison
from tests.app.use_cases.test_analysis_comparison_edges import selection


def save_legacy(comparison: AnalysisComparisonService) -> str:
    pair = selection().pairs[0]
    inspected = comparison.compare(pair)
    cohort = SavedCohort(
        cohort_id="legacy",
        created_at="2026-10-03T00:00:00+00:00",
        selection=selection(),
        runs=(
            PinnedComparison(
                pair=pair,
                paper_id="paper-a",
                baseline_sha256=hashlib.sha256(
                    inspected.baseline.model_dump_json().encode()
                ).hexdigest(),
                revised_sha256=hashlib.sha256(
                    inspected.revised.model_dump_json().encode()
                ).hexdigest(),
            ),
        ),
    )
    AnalysisCohortStore(comparison.database).save(cohort)
    encoded = cohort.model_dump_json(exclude={"fingerprint_version"})
    comparison.database.execute(
        "UPDATE analysis_evaluation_cohorts SET document_json=? WHERE cohort_id=?",
        [encoded, cohort.cohort_id],
    )
    return encoded


def test_legacy_api_reopen_and_explicit_resave_preserve_authority_json(
    comparison: AnalysisComparisonService, tmp_path: Path
) -> None:
    encoded = save_legacy(comparison)
    config = tmp_path / "legacy.toml"
    config.write_text(f'[data]\ndb_path = "{comparison.database.path}"\n')
    client = GleansightAPI(ApiConfiguration(repo_root=tmp_path, config_path=config))
    opened = client.call("papers.analysis.cohorts.compare", {"cohort_id": "legacy"})
    assert isinstance(opened, Success), opened
    fresh = client.call(
        "papers.analysis.cohorts.save", {"selection": selection().model_dump(mode="json")}
    )
    assert isinstance(fresh, Success), fresh
    saved = SavedCohort.model_validate(fresh.data)
    assert saved.fingerprint_version == 2
    for run_id in ("run-1", "run-2"):
        original = artifact_path(comparison.inspect(run_id)).parent
        relocated = tmp_path / "relocated" / run_id
        shutil.copytree(original, relocated)
        comparison.database.execute(
            "UPDATE analysis_runs SET output_blob_path_md=?, output_blob_path_json=? "
            "WHERE run_id=?",
            [str(relocated / "output.md"), str(relocated / "output.json"), run_id],
        )
    assert comparison.compare_cohort(saved.cohort_id).cohort == saved
    with pytest.raises(
        ValueError, match="Re-save the cohort in its original workspace before backup"
    ):
        comparison.compare_cohort("legacy")
    assert comparison.database.fetchone(
        "SELECT document_json FROM analysis_evaluation_cohorts WHERE cohort_id='legacy'"
    ) == {"document_json": encoded}
    (tmp_path / "legacy-reopen-result.json").write_text(opened.model_dump_json(indent=2))


@pytest.mark.parametrize(
    "mutation",
    [
        "metadata_bytes",
        "metadata_fields",
        "output",
        "json",
        "status",
        "validation",
        "tokens",
        "schema",
        "symlink",
    ],
)
def test_content_pins_reject_real_changes(
    comparison: AnalysisComparisonService, mutation: str
) -> None:
    saved = comparison.save_cohort(selection())
    output = artifact_path(comparison.inspect("run-1"))
    metadata = output.parent / "meta.json"
    match mutation:
        case "metadata_bytes":
            metadata.write_text(metadata.read_text() + "\n")
        case "metadata_fields":
            content = json.loads(metadata.read_text())
            content["review_note"] = "changed provenance"
            metadata.write_text(json.dumps(content))
        case "output":
            output.write_text("different output")
        case "json":
            (output.parent / "output.json").write_text('{"score":999}')
        case "status":
            comparison.database.execute("UPDATE jobs SET status='failed' WHERE run_id='run-1'")
        case "validation":
            comparison.database.execute(
                "UPDATE analysis_runs SET validation_issues_json='[1]' WHERE run_id='run-1'"
            )
        case "tokens":
            comparison.database.execute(
                "UPDATE analysis_runs SET tokens_in=99 WHERE run_id='run-1'"
            )
        case "schema":
            comparison.database.execute(
                "UPDATE prompt_versions SET extraction_schema_json='{}' "
                "WHERE prompt_version_id='prompt-1'"
            )
        case "symlink":
            target = metadata.with_name("metadata-copy.json")
            metadata.rename(target)
            metadata.symlink_to(target)
    with pytest.raises(ValueError, match="source has changed"):
        comparison.compare_cohort(saved.cohort_id)
