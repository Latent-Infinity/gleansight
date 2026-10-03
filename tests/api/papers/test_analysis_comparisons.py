from __future__ import annotations

from pathlib import Path

import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure, Success
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.domain.analysis_comparison import RunComparison, RunInspection, SavedCohort
from tests.app.use_cases.test_analysis_comparison import comparison as comparison
from tests.app.use_cases.test_analysis_comparison_edges import selection


def test_public_cohort_survives_client_restart_without_providers(
    comparison: AnalysisComparisonService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given real stored runs, a workspace configuration, and forbidden provider composition.
    config = tmp_path / "comparison.toml"
    config.write_text(f'[data]\ndb_path = "{comparison.database.path}"\n')
    configuration = ApiConfiguration(repo_root=tmp_path, config_path=config)

    def forbidden(_: ApiRuntime) -> None:
        pytest.fail("Read-only comparison initialized heavy providers")

    monkeypatch.setattr(ApiRuntime, "papers", property(forbidden))
    client = GleansightAPI(configuration)
    saved = client.call(
        "papers.analysis.cohorts.save", {"selection": selection().model_dump(mode="json")}
    )
    assert isinstance(saved, Success)
    cohort = SavedCohort.model_validate(saved.data)
    # When a new public client reads and compares that immutable saved selection.
    restarted = GleansightAPI(configuration)
    result = restarted.call("papers.analysis.cohorts.compare", {"cohort_id": cohort.cohort_id})
    retrieved = restarted.call("papers.analysis.cohorts.get", {"cohort_id": cohort.cohort_id})
    listed = restarted.call("papers.analysis.cohorts.list", {})
    # Then exact saved IDs remain available through the public boundary.
    assert isinstance(result, Success)
    assert isinstance(retrieved, Success)
    assert SavedCohort.model_validate(retrieved.data) == cohort
    assert isinstance(listed, Success)
    assert isinstance(listed.data, list) and len(listed.data) == 1
    (tmp_path / "api-cohort-result.json").write_text(result.model_dump_json(indent=2))


def test_public_inspection_and_compare_preserve_failed_status(
    comparison: AnalysisComparisonService, tmp_path: Path
) -> None:
    # Given two stored runs in a configured public client.
    config = tmp_path / "comparison.toml"
    config.write_text(f'[data]\ndb_path = "{comparison.database.path}"\n')
    client = GleansightAPI(ApiConfiguration(repo_root=tmp_path, config_path=config))
    # When both public read operations execute.
    opened = client.call("papers.analysis.inspect", {"run_id": "run-2"})
    compared = client.call(
        "papers.analysis.compare", {"baseline_run_id": "run-1", "revised_run_id": "run-2"}
    )
    # Then output and failed validation are returned, without normalizing away failure.
    assert isinstance(opened, Success)
    assert RunInspection.model_validate(opened.data).status == "failed"
    assert isinstance(compared, Success)
    assert RunComparison.model_validate(compared.data).schema_changed
    (tmp_path / "api-comparison-result.json").write_text(compared.model_dump_json(indent=2))


@pytest.mark.parametrize(
    "operation, parameters, code",
    [
        ("papers.analysis.inspect", {"run_id": "missing"}, "not_found"),
        ("papers.analysis.cohorts.get", {"cohort_id": "missing"}, "not_found"),
        (
            "papers.analysis.compare",
            {"baseline_run_id": "same", "revised_run_id": "same"},
            "invalid_request",
        ),
        ("papers.analysis.inspect", {"run_id": "run-1", "unexpected": True}, "invalid_request"),
    ],
)
def test_public_errors_are_structured(
    tmp_path: Path, operation: str, parameters: dict[str, str | bool], code: str
) -> None:
    # Given a fresh workspace client.
    client = GleansightAPI(ApiConfiguration(repo_root=tmp_path))
    # When an invalid/missing selection is sent.
    result = client.call(operation, parameters)
    # Then the stable public error category survives the transport.
    assert isinstance(result, Failure)
    assert result.error.code == code
