from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from research.catalog.artifacts import document, mapping, verified_artifacts
from research.catalog.diagnostics import metric
from research.catalog.models import CatalogError, Digest, RunMetric, VerifiedRun, json_digest


def verify_baseline(path: Path) -> VerifiedRun:
    metadata, hashes, metadata_sha = verified_artifacts(
        path, frozenset({"protocol.json", "source-metadata.json", "results.json", "report.md"})
    )
    if (
        metadata.get("workflow") != "financial-jepa"
        or metadata.get("completion_state") != "complete"
    ):
        raise CatalogError("YieldJEPA bundle is incomplete or has the wrong workflow")
    source = document(path / "source-metadata.json")
    source_bytes = (
        json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if (
        metadata.get("protocol_sha256") != hashes["protocol.json"]
        or metadata.get("source_metadata_sha256") != source_sha
    ):
        raise CatalogError("YieldJEPA protocol/source identity mismatch")
    protocol, results = document(path / "protocol.json"), document(path / "results.json")
    if protocol.get("protocol_version") != "yield-jepa/1" or protocol.get("status") not in (
        "canonical",
        "synthetic_test_only",
    ):
        raise CatalogError("Unsupported YieldJEPA protocol or research classification")
    code = mapping(metadata["code_identity"])
    seeds = TypeAdapter(tuple[int, ...]).validate_python(mapping(protocol["training"])["seeds"])
    rows: list[RunMetric] = []
    baselines = mapping(results["raw_baselines"])
    for name in ("direct_ridge", "last_level_persistence", "training_row_mean"):
        baseline = mapping(baselines[name])
        rows.append(
            metric(name, None, baseline, {"model_identity": baseline.get("model_identity")})
        )
    dates = {TypeAdapter(Digest).validate_python(baselines["date_sha256"])}
    for fit in TypeAdapter(list[dict[str, JsonValue]]).validate_python(results["fits"]):
        seed = TypeAdapter(int).validate_python(fit["seed"])
        if seed not in seeds:
            raise CatalogError("YieldJEPA result seed was not declared by the protocol")
        dates.add(TypeAdapter(Digest).validate_python(fit["date_sha256"]))
        rows.append(
            metric(
                TypeAdapter(str).validate_python(fit["variant"]),
                seed,
                mapping(fit["raw_metrics"]),
                {key: fit[key] for key in ("checkpoint_sha256", "readout_sha256")},
            )
        )
    if len(dates) != 1:
        raise CatalogError("YieldJEPA fits do not share one paired date identity")
    return VerifiedRun(
        run_id=json_digest(
            TypeAdapter(JsonValue).validate_python({"metadata": metadata_sha, "artifacts": hashes})
        ),
        declared_run_id=TypeAdapter(str).validate_python(metadata["run_id"]),
        workflow="financial-jepa",
        classification="smoke"
        if protocol["status"] == "synthetic_test_only"
        else "evaluation_record",
        verification="artifact_hashes",
        source_sha256=source_sha,
        protocol_sha256=hashes["protocol.json"],
        split_sha256=json_digest(mapping(protocol["dataset"])["splits"]),
        code_sha256=TypeAdapter(Digest).validate_python(code["sha256"]),
        metadata_sha256=metadata_sha,
        artifact_sha256=hashes,
        code_files=TypeAdapter(dict[str, Digest]).validate_python(code["files"]),
        seeds=seeds,
        origin_dates=(),
        target_dates=(),
        date_sha256=next(iter(dates)),
        metrics=tuple(rows),
        limitations=(
            "Saved metrics are hash-verified, not reconstructed from frozen forecasts.",
            "Exact paired dates are absent; numerical cross-run comparison is unavailable.",
        ),
    )
