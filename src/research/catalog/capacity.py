from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from research.catalog.artifacts import mapping, verified_artifacts
from research.catalog.diagnostics import metric
from research.catalog.models import Digest, MetricDefinition, RunMetric, VerifiedRun, json_digest
from research.financial_jepa.capacity_models import Trial
from research.financial_jepa.capacity_validation import verify_capacity_bundle
from research.financial_jepa.contracts import TENOR_FIELDS
from research.financial_jepa.evaluation import metric_summary
from research.financial_jepa.reporting import metric_record


def verify_capacity(path: Path) -> VerifiedRun:
    _, hashes, metadata_sha = verified_artifacts(
        path, frozenset({"document.json", "fits.npz", "report.md"})
    )
    bundle = verify_capacity_bundle(path)
    doc = bundle.document
    protocol, membership = mapping(doc["protocol"]), mapping(doc["membership"])
    code = TypeAdapter(dict[str, Digest]).validate_python(doc["code_sha256"])
    origin = TypeAdapter(tuple[date, ...]).validate_python(membership["selection_origin_dates"])
    targets = TypeAdapter(tuple[tuple[date, ...], ...]).validate_python(
        membership["selection_target_dates"]
    )
    rows: list[RunMetric] = []
    for trial in TypeAdapter(tuple[Trial, ...]).validate_python(doc["trials"]):
        identity = TypeAdapter(dict[str, JsonValue]).validate_python(trial.model_dump(mode="json"))
        if trial.status == "failed":
            rows.append(
                RunMetric(
                    method=trial.method,
                    seed=trial.seed,
                    values=None,
                    definition=MetricDefinition(tenor_fields=TENOR_FIELDS),
                    artifact_identity=identity,
                    problem=trial.error,
                )
            )
        else:
            actual = bundle.arrays["actual_selection_targets"]
            forecast = bundle.arrays[f"seed_{trial.seed}.{trial.method}.forecast"]
            rows.append(
                metric(
                    trial.method,
                    trial.seed,
                    metric_record(metric_summary(actual, forecast)),
                    identity,
                )
            )
    return VerifiedRun(
        run_id=json_digest(
            TypeAdapter(JsonValue).validate_python(
                {"directory_run_id": path.name, "metadata": metadata_sha, "artifacts": hashes}
            )
        ),
        declared_run_id=path.name,
        workflow="financial-jepa-capacity",
        classification="development_diagnostic",
        verification="reconstructed_capacity",
        source_sha256=json_digest(protocol["source_artifact_sha256"]),
        protocol_sha256=TypeAdapter(Digest).validate_python(doc["protocol_sha256"]),
        split_sha256=TypeAdapter(Digest).validate_python(doc["membership_sha256"]),
        code_sha256=json_digest(TypeAdapter(JsonValue).validate_python(code)),
        metadata_sha256=metadata_sha,
        artifact_sha256=hashes,
        code_files=code,
        seeds=TypeAdapter(tuple[int, ...]).validate_python(protocol["seeds"]),
        origin_dates=origin,
        target_dates=targets,
        date_sha256=json_digest(
            {
                "origins": [day.isoformat() for day in origin],
                "targets": [[day.isoformat() for day in days] for days in targets],
            }
        ),
        metrics=tuple(rows),
        limitations=(
            "Development selection is not held-out evaluation.",
            "Capacity format identifies the selected run by directory name; "
            "artifact hashes remain explicit.",
        ),
    )
