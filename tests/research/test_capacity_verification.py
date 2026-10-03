from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import JsonValue, TypeAdapter

from research.financial_jepa.capacity_fitting import run_trial
from research.financial_jepa.capacity_models import FeaturePair, Trial
from research.financial_jepa.capacity_reporting import summary
from research.financial_jepa.capacity_storage import load_bundle, write_bundle
from research.financial_jepa.capacity_validation import METHODS, verify_capacity_bundle
from research.financial_jepa.contracts import ALPHAS, SEEDS, ProtocolError
from research.financial_jepa.diagnostic_artifacts import ARTIFACT_FILES
from research.financial_jepa.walkforward_protocol import digest


@pytest.fixture(scope="module")
def verified_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("capacity") / "complete"
    rng = np.random.default_rng(29)
    train_targets, selection_targets = rng.normal(size=(50, 5, 8)), rng.normal(size=(12, 5, 8))
    trials, arrays = [], {"actual_selection_targets": selection_targets}
    for seed in SEEDS:
        for method, (group, budget, dimensions) in METHODS.items():
            shape = (
                (5, dimensions)
                if method.endswith("predicted")
                else (budget if method.startswith("raw") else 16,)
            )
            pair = FeaturePair(
                method,
                "current" if group == "current" else "history",
                seed,
                budget,
                rng.normal(size=(50, *shape)),
                rng.normal(size=(12, *shape)),
                train_targets,
                selection_targets,
            )
            trial, fitted = run_trial(pair)
            assert trial.status == "ok"
            trials.append(trial)
            arrays.update({f"seed_{seed}.{method}.{key}": value for key, value in fitted.items()})
    protocol: dict[str, JsonValue] = {
        "version": "yield-jepa-capacity/1",
        "status": "development_selection",
        "input_readout_groups": {"current": [8, 8], "history": [240, 16]},
        "seeds": list(SEEDS),
        "ridge_alphas": list(ALPHAS),
        "deadline_seconds": 900,
        "neural_fit_count": 0,
        "ridge_candidate_count": 360,
        "selection": "fixture development selection",
        "source_artifact_sha256": {
            name: "a" * 64 for name in (*ARTIFACT_FILES, "run-metadata.json")
        },
    }
    membership: dict[str, JsonValue] = {}
    for partition, year, count in (("train", 2017, 50), ("selection", 2018, 12)):
        origins = [date(year, 1, 1) + timedelta(days=index) for index in range(count)]
        membership[f"{partition}_origin_dates"] = [day.isoformat() for day in origins]
        membership[f"{partition}_target_dates"] = [
            [(day + timedelta(days=offset)).isoformat() for offset in range(1, 6)]
            for day in origins
        ]
    document: dict[str, JsonValue] = {
        "protocol": protocol,
        "protocol_sha256": digest(protocol),
        "membership": membership,
        "membership_sha256": digest(membership),
        "code_sha256": {"fixture.py": "b" * 64},
        "trials": [
            TypeAdapter(dict[str, JsonValue]).validate_python(trial.model_dump(mode="json"))
            for trial in trials
        ],
        "aggregates": summary(tuple(trials)),
    }
    write_bundle(root, document, arrays)
    verify_capacity_bundle(root)
    return root


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "label",
        "seed",
        "provenance",
        "hash",
        "future",
        "duplicate_dates",
        "target",
        "trial_seed",
        "budget",
        "metric",
        "ridge",
        "rank",
        "projection",
        "aggregate",
        "extra_array",
    ],
)
def test_rehashed_semantic_tampering_is_refused(
    verified_fixture: Path, tmp_path: Path, mutation: str
) -> None:
    loaded = load_bundle(verified_fixture)
    document, arrays = loaded.document, loaded.arrays
    protocol, membership, trials = document["protocol"], document["membership"], document["trials"]
    assert isinstance(protocol, dict) and isinstance(membership, dict) and isinstance(trials, list)
    first = trials[0]
    assert isinstance(first, dict)
    match mutation:
        case "schema":
            document["unexpected"] = True
        case "label":
            protocol["status"] = "heldout"
        case "seed":
            protocol["seeds"] = [99]
        case "provenance":
            protocol["source_artifact_sha256"] = {}
        case "hash":
            document["code_sha256"] = {"code": "bad"}
        case "future":
            membership["selection_origin_dates"] = ["2022-01-01"] * 12
        case "duplicate_dates":
            membership["train_origin_dates"] = ["2017-01-01"] * 50
        case "target":
            arrays["actual_selection_targets"] = np.zeros((12, 4, 8))
        case "trial_seed":
            first["seed"] = 99
        case "budget":
            first["readout_features"] = 16
        case "metric":
            first["rmse_bp"] = 0
        case "ridge":
            arrays["seed_17.raw_current.ridge_0_coefficients"] = np.zeros((1, 1))
        case "rank":
            first["training_feature_rank"] = 99
        case "projection":
            projected = trials[1]
            assert isinstance(projected, dict)
            projected["projection_variance_retained"] = None
        case "aggregate":
            document["aggregates"] = {}
        case "extra_array":
            arrays["unexpected"] = np.zeros(1)
    document["protocol_sha256"] = digest(protocol)
    document["membership_sha256"] = digest(membership)
    changed = tmp_path / "changed"
    write_bundle(changed, document, arrays)
    with pytest.raises(ProtocolError):
        verify_capacity_bundle(changed)


def test_valid_failed_trial_is_preserved_with_excluded_pair_count(
    verified_fixture: Path, tmp_path: Path
) -> None:
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
    destination = tmp_path / "failed-trial"
    write_bundle(destination, loaded.document, arrays)
    verified = verify_capacity_bundle(destination)
    aggregate = verified.document["aggregates"]
    assert isinstance(aggregate, dict)
    failures = aggregate["failures"]
    assert isinstance(failures, list) and len(failures) == 1
    assert aggregate["paired"] == summary(tuple(trials))["paired"]


@pytest.mark.parametrize(
    "mutation",
    [
        "protocol_hash",
        "membership_hash",
        "membership_schema",
        "resource",
        "future_targets",
        "forecast",
        "failure",
        "projection_shape",
        "projection_loss",
    ],
)
def test_additional_selection_and_state_refusals(
    verified_fixture: Path, tmp_path: Path, mutation: str
) -> None:
    loaded = load_bundle(verified_fixture)
    document, arrays = loaded.document, loaded.arrays
    protocol, membership, trials = document["protocol"], document["membership"], document["trials"]
    assert isinstance(protocol, dict) and isinstance(membership, dict) and isinstance(trials, list)
    first = trials[0]
    assert isinstance(first, dict)
    match mutation:
        case "protocol_hash":
            document["protocol_sha256"] = "a" * 64
        case "membership_hash":
            document["membership_sha256"] = "a" * 64
        case "membership_schema":
            document["membership"] = {}
        case "resource":
            protocol["deadline_seconds"] = 999
            document["protocol_sha256"] = digest(protocol)
        case "future_targets":
            membership["selection_target_dates"] = [
                [f"2022-01-0{index}" for index in range(1, 6)] for _ in range(12)
            ]
            document["membership_sha256"] = digest(membership)
        case "forecast":
            arrays.pop("seed_17.raw_current.forecast")
        case "failure":
            first["status"] = "failed"
        case "projection_shape":
            arrays["seed_17.selected_current_pca.projection_components"] = np.ones((1, 1))
        case "projection_loss":
            arrays["seed_17.selected_current_pca.projection_variance_fraction"] = np.asarray(0.0)
    destination = tmp_path / "invalid"
    write_bundle(destination, document, arrays)
    with pytest.raises(ProtocolError):
        verify_capacity_bundle(destination)
