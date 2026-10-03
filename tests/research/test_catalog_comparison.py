from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from research.catalog.comparison import compare_runs
from research.catalog.models import MetricValues
from research.catalog.verify import verify_bundle
from tests.research.test_capacity_verification import verified_fixture as verified_fixture


def test_metric_contract_rejects_negative_axis_and_inconsistent_matrix() -> None:
    with pytest.raises(ValidationError):
        MetricValues(
            overall_rmse_bp=1,
            per_horizon_rmse_bp=(-1,),
            per_tenor_rmse_bp=(1,),
            matrix_rmse_bp=((1,),),
        )
    with pytest.raises(ValidationError):
        MetricValues(
            overall_rmse_bp=1,
            per_horizon_rmse_bp=(1, 2),
            per_tenor_rmse_bp=(1,),
            matrix_rmse_bp=((1,),),
        )


@pytest.mark.parametrize(
    "field",
    [
        "source_sha256",
        "protocol_sha256",
        "split_sha256",
        "code_sha256",
        "seeds",
        "origin_dates",
        "target_dates",
        "classification",
        "verification",
    ],
)
def test_explicit_incompatible_identity_refuses_numeric_comparison(
    verified_fixture: Path, field: str
) -> None:
    run = verify_bundle(verified_fixture)
    changes = {
        "source_sha256": "e" * 64,
        "protocol_sha256": "e" * 64,
        "split_sha256": "e" * 64,
        "code_sha256": "e" * 64,
        "seeds": (17,),
        "origin_dates": (),
        "target_dates": (),
        "classification": "smoke",
        "verification": "artifact_hashes",
    }
    other = run.model_copy(update={"run_id": "f" * 64, field: changes[field]})
    result = compare_runs((run, other))
    assert not result.comparable and not result.pairs and result.winner is None
    assert field in {issue.field for issue in result.issues}


def test_methods_definitions_and_unavailable_failures_are_explicit(verified_fixture: Path) -> None:
    run = verify_bundle(verified_fixture)
    other = run.model_copy(update={"run_id": "f" * 64, "metrics": run.metrics[:-1]})
    assert compare_runs((run, other)).issues[0].field == "methods"
    altered = run.metrics[0].model_copy(
        update={
            "definition": run.metrics[0].definition.model_copy(update={"task": "reconstruction"})
        }
    )
    other = other.model_copy(update={"metrics": (altered, *run.metrics[1:])})
    assert compare_runs((run, other)).issues[0].field == "metric_definitions"
    failed = run.metrics[0].model_copy(update={"values": None, "problem": "declared failed trial"})
    other = other.model_copy(update={"metrics": (failed, *run.metrics[1:])})
    result = compare_runs((run, other))
    assert result.comparable and result.pairs[0].right is None
    assert result.pairs[0].right_minus_left_rmse_bp is None
    assert len(result.pairs) == 18 and result.winner is None


def test_duplicate_method_seed_identity_cannot_be_a_verified_record(verified_fixture: Path) -> None:
    run = verify_bundle(verified_fixture)
    with pytest.raises(ValidationError):
        type(run).model_validate({**run.model_dump(), "metrics": (*run.metrics, run.metrics[0])})


def test_incomparable_report_is_a_separate_artifact(verified_fixture: Path, tmp_path: Path) -> None:
    import json

    from research.catalog.output import write_comparison

    run = verify_bundle(verified_fixture)
    other = run.model_copy(update={"run_id": "f" * 64, "source_sha256": "e" * 64})
    report = compare_runs((run, other))
    path = write_comparison(tmp_path, report)
    assert json.loads((path / "comparison.json").read_text())["comparable"] is False
    assert "source_sha256 differs" in (path / "report.md").read_text()
    assert "## Paired descriptive RMSE" not in (path / "report.md").read_text()


def test_actual_verified_failed_capacity_trial_has_no_fabricated_score(
    verified_fixture: Path, tmp_path: Path
) -> None:
    from pydantic import JsonValue, TypeAdapter

    from research.financial_jepa.capacity_models import Trial
    from research.financial_jepa.capacity_reporting import summary
    from research.financial_jepa.capacity_storage import load_bundle, write_bundle

    loaded = load_bundle(verified_fixture)
    trials = list(TypeAdapter(tuple[Trial, ...]).validate_python(loaded.document["trials"]))
    trials[0] = trials[0].model_copy(
        update={
            "status": "failed",
            "error": "declared numerical fit failure",
            "rmse_bp": None,
            "selected_alpha": None,
            "per_horizon_rmse_bp": (),
        }
    )
    loaded.document["trials"] = [
        TypeAdapter(dict[str, JsonValue]).validate_python(trial.model_dump(mode="json"))
        for trial in trials
    ]
    loaded.document["aggregates"] = summary(tuple(trials))
    arrays = {
        name: value
        for name, value in loaded.arrays.items()
        if not name.startswith("seed_17.raw_current.")
    }
    path = tmp_path / "failure-preserved"
    write_bundle(path, loaded.document, arrays)
    record = verify_bundle(path)
    failed = next(metric for metric in record.metrics if metric.problem is not None)
    assert failed.values is None and failed.problem == "declared numerical fit failure"
    assert len(record.metrics) == 18
