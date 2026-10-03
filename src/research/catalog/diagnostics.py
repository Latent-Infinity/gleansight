from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from research.catalog.artifacts import mapping, verified_artifacts
from research.catalog.models import (
    CatalogError,
    Digest,
    MetricDefinition,
    MetricValues,
    RunMetric,
    VerifiedRun,
    json_digest,
)
from research.financial_jepa.contracts import TENOR_FIELDS
from research.financial_jepa.diagnostic_artifacts import ARTIFACT_FILES
from research.financial_jepa.diagnostic_reload import reload_and_verify


def metric(
    method: str,
    seed: int | None,
    value: dict[str, JsonValue],
    identity: dict[str, JsonValue],
    *,
    reconstruction: bool = False,
) -> RunMetric:
    values = MetricValues.model_validate({key: value[key] for key in MetricValues.model_fields})
    return RunMetric(
        method=method,
        seed=seed,
        values=values,
        artifact_identity=identity,
        definition=MetricDefinition(
            tenor_fields=TENOR_FIELDS, task="reconstruction" if reconstruction else "forecast"
        ),
    )


def verify_diagnostics(path: Path) -> VerifiedRun:
    metadata, hashes, metadata_sha = verified_artifacts(path, frozenset(ARTIFACT_FILES))
    verified = reload_and_verify(path)
    bundle = verified.bundle
    protocol, results = bundle.protocol, bundle.results
    status = protocol["status"]
    if status not in ("synthetic_test_only", "development_selection"):
        raise CatalogError("Unsupported diagnostic research classification")
    code = mapping(metadata["code_identity"])
    seeds = TypeAdapter(tuple[int, ...]).validate_python(mapping(protocol["training"])["seeds"])
    origin = TypeAdapter(tuple[date, ...]).validate_python(
        bundle.validation["origin_dates"].tolist()
    )
    targets = TypeAdapter(tuple[tuple[date, ...], ...]).validate_python(
        bundle.validation["target_dates"].tolist()
    )
    rows = [
        metric("raw_history", None, mapping(mapping(results["methods"])["raw_history"]), {}),
        metric("persistence", None, mapping(results["persistence"]), {}),
    ]
    for raw in TypeAdapter(list[dict[str, JsonValue]]).validate_python(results["seeds"]):
        seed = TypeAdapter(int).validate_python(raw["seed"])
        identity = {key: raw[key] for key in ("selected_state_sha256", "initial_state_sha256")}
        for method, value in mapping(raw["methods"]).items():
            rows.append(metric(method, seed, mapping(value), identity))
        rows.append(
            metric(
                "current_reconstruction",
                seed,
                mapping(raw["current_reconstruction"]),
                identity,
                reconstruction=True,
            )
        )
    split: dict[str, JsonValue] = {
        "declared_splits": mapping(protocol["dataset"])["splits"],
        "train_rows": bundle.validation["train_row_dates"].tolist(),
        "origins": [day.isoformat() for day in origin],
        "targets": [[day.isoformat() for day in days] for days in targets],
    }
    return VerifiedRun(
        run_id=json_digest(
            TypeAdapter(JsonValue).validate_python({"metadata": metadata_sha, "artifacts": hashes})
        ),
        declared_run_id=TypeAdapter(str).validate_python(metadata["run_id"]),
        workflow="financial-jepa-diagnostics",
        classification="smoke" if status == "synthetic_test_only" else "development_diagnostic",
        verification="reconstructed_forecasts",
        source_sha256=TypeAdapter(Digest).validate_python(metadata["source_metadata_sha256"]),
        protocol_sha256=hashes["protocol.json"],
        split_sha256=json_digest(split),
        code_sha256=TypeAdapter(Digest).validate_python(code["sha256"]),
        metadata_sha256=metadata_sha,
        artifact_sha256=hashes,
        code_files=TypeAdapter(dict[str, Digest]).validate_python(code["files"]),
        seeds=seeds,
        origin_dates=origin,
        target_dates=targets,
        date_sha256=TypeAdapter(Digest).validate_python(results["date_sha256"]),
        metrics=tuple(rows),
        limitations=("Development selection is not held-out evaluation.",),
    )
