from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import TypeAdapter

from research.financial_jepa.capacity_models import Trial
from research.financial_jepa.capacity_reporting import summary
from research.financial_jepa.capacity_storage import LoadedCapacityBundle, load_bundle
from research.financial_jepa.contracts import ALPHAS, SEEDS, ProtocolError
from research.financial_jepa.diagnostic_artifacts import ARTIFACT_FILES
from research.financial_jepa.evaluation import metric_summary
from research.financial_jepa.walkforward_protocol import digest

METHODS = {
    "raw_current": ("current", 8, 8),
    "selected_current_pca": ("current", 8, 8),
    "random_current_pca": ("current", 8, 8),
    "raw_history_pca": ("history", 240, 16),
    "selected_predicted": ("history", 240, 16),
    "random_predicted": ("history", 240, 16),
}


def verify_capacity_bundle(path: Path) -> LoadedCapacityBundle:
    bundle = load_bundle(path)
    document = bundle.document
    if set(document) != {
        "protocol",
        "protocol_sha256",
        "membership",
        "membership_sha256",
        "code_sha256",
        "trials",
        "aggregates",
    }:
        raise ProtocolError("capacity document schema disagrees")
    protocol = document["protocol"]
    if (
        not isinstance(protocol, dict)
        or protocol.get("version") != "yield-jepa-capacity/1"
        or protocol.get("status") != "development_selection"
    ):
        raise ProtocolError("capacity protocol or selection label disagrees")
    if (
        protocol.get("seeds") != list(SEEDS)
        or protocol.get("ridge_alphas") != list(ALPHAS)
        or protocol.get("input_readout_groups") != {"current": [8, 8], "history": [240, 16]}
    ):
        raise ProtocolError("capacity seed, alpha or budget schema disagrees")
    if document["protocol_sha256"] != digest(protocol):
        raise ProtocolError("capacity protocol identity disagrees")
    source = protocol.get("source_artifact_sha256")
    if not isinstance(source, dict) or set(source) != {*ARTIFACT_FILES, "run-metadata.json"}:
        raise ProtocolError("capacity selection provenance is incomplete")
    if (
        set(protocol)
        != {
            "version",
            "status",
            "input_readout_groups",
            "seeds",
            "ridge_alphas",
            "deadline_seconds",
            "selection",
            "neural_fit_count",
            "ridge_candidate_count",
            "source_artifact_sha256",
        }
        or protocol.get("deadline_seconds") != 900
        or protocol.get("neural_fit_count") != 0
        or protocol.get("ridge_candidate_count") != 360
    ):
        raise ProtocolError("capacity frozen resource protocol disagrees")
    for identities in (source, document["code_sha256"]):
        if (
            not isinstance(identities, dict)
            or not identities
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in identities.values()
            )
        ):
            raise ProtocolError("capacity source/code identity is invalid")
    membership = document["membership"]
    if not isinstance(membership, dict) or set(membership) != {
        "train_origin_dates",
        "selection_origin_dates",
        "train_target_dates",
        "selection_target_dates",
    }:
        raise ProtocolError("capacity membership schema disagrees")
    if document["membership_sha256"] != digest(membership):
        raise ProtocolError("capacity membership identity disagrees")
    sizes = {}
    for partition, lower, upper in (("train", 2001, 2017), ("selection", 2018, 2021)):
        origins = TypeAdapter(list[date]).validate_python(membership[f"{partition}_origin_dates"])
        targets = TypeAdapter(list[list[date]]).validate_python(
            membership[f"{partition}_target_dates"]
        )
        if not origins or len(origins) != len(targets) or origins != sorted(set(origins)):
            raise ProtocolError("capacity dates must be unique, aligned and chronological")
        for origin, future in zip(origins, targets, strict=True):
            if (
                len(future) != 5
                or future != sorted(set(future))
                or origin >= future[0]
                or any(day.year < lower or day.year > upper for day in [origin, *future])
            ):
                raise ProtocolError("capacity dates cross partition or reserved boundaries")
        sizes[partition] = len(origins)
    actual = bundle.arrays.get("actual_selection_targets")
    if actual is None or actual.shape != (sizes["selection"], 5, 8):
        raise ProtocolError("capacity target schema disagrees")
    trials = TypeAdapter(tuple[Trial, ...]).validate_python(document["trials"])
    if len(trials) != 18 or {(trial.seed, trial.method) for trial in trials} != {
        (seed, method) for seed in SEEDS for method in METHODS
    }:
        raise ProtocolError("capacity paired seeds or methods are incomplete")
    expected_arrays = {"actual_selection_targets"}
    for trial in trials:
        group, budget, dimensions = METHODS[trial.method]
        if (
            trial.group,
            trial.input_budget,
            trial.readout_features,
            trial.readout_parameters,
            trial.train_rows,
            trial.selection_rows,
        ) != (group, budget, dimensions, (dimensions + 1) * 40, sizes["train"], sizes["selection"]):
            raise ProtocolError("capacity trial input/readout/date budget disagrees")
        prefix = f"seed_{trial.seed}.{trial.method}."
        if trial.status == "failed":
            if not trial.error or trial.rmse_bp is not None or trial.selected_alpha is not None:
                raise ProtocolError("capacity failure record disagrees")
            continue
        forecast = bundle.arrays.get(prefix + "forecast")
        if forecast is None or forecast.shape != actual.shape or trial.selected_alpha not in ALPHAS:
            raise ProtocolError("capacity forecast or selection schema disagrees")
        metric = metric_summary(actual, forecast)
        if (
            trial.rmse_bp != metric.overall_rmse_bp
            or trial.per_horizon_rmse_bp != metric.per_horizon_rmse_bp
        ):
            raise ProtocolError("capacity metrics disagree with saved forecasts")
        expected_arrays.add(prefix + "forecast")
        for horizon in range(5):
            for key, shape in (
                ("coefficients", (dimensions, 8)),
                ("intercept", (8,)),
                ("mean", (dimensions,)),
                ("std", (dimensions,)),
            ):
                name = prefix + f"ridge_{horizon}_{key}"
                if name not in bundle.arrays or bundle.arrays[name].shape != shape:
                    raise ProtocolError("capacity selected readout state is incomplete")
                expected_arrays.add(name)
        if trial.method.endswith("pca"):
            source_dimensions = 240 if trial.method == "raw_history_pca" else 16
            projection_shapes = {
                "projection_mean": (source_dimensions,),
                "projection_std": (source_dimensions,),
                "projection_components": (dimensions, source_dimensions),
                "projection_variance_fraction": (),
            }
            for key in (
                "projection_mean",
                "projection_std",
                "projection_components",
                "projection_variance_fraction",
            ):
                if (
                    prefix + key not in bundle.arrays
                    or bundle.arrays[prefix + key].shape != projection_shapes[key]
                ):
                    raise ProtocolError("capacity projection state schema disagrees")
                expected_arrays.add(prefix + key)
            if (
                trial.projection_variance_retained is None
                or not 0 <= trial.projection_variance_retained <= 1.0000000001
            ):
                raise ProtocolError("capacity projection information loss is missing")
            if (
                float(bundle.arrays[prefix + "projection_variance_fraction"])
                != trial.projection_variance_retained
            ):
                raise ProtocolError("capacity projection information loss disagrees")
        if (
            trial.training_feature_rank is None
            or not 0 <= trial.training_feature_rank <= dimensions
        ):
            raise ProtocolError("capacity numerical feature rank is invalid")
    if set(bundle.arrays) != expected_arrays:
        raise ProtocolError("capacity arrays have missing or unexpected state")
    if document["aggregates"] != summary(trials):
        raise ProtocolError("capacity paired aggregates or failures disagree")
    return bundle
