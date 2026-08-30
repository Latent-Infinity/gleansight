from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from nsqd.domain.novelty import NOVELTY_K, mean_cosine_distance
from nsqd.domain.project import (
    PROJECTOR_VERSION,
    canonical_reviewed_projection_digest,
    normalize_paraphrase,
)
from nsqd.domain.snapshot import canonical_json, normalize_source, sha256_hex

TAU_MEASUREMENT_POLICIES = ("finance/1", "optimization/1")
BLOCKED_TAU_SOURCE_CLASSES = frozenset(
    {"synthetic", "llm_invented", "requirement_card", "unapproved"}
)
REQUIRED_STAMP_FIELDS = (
    "embedding_model_id",
    "embedding_model_version",
    "embedding_dimension",
    "normalization_policy",
    "distance_metric",
    "algorithm_contract_version",
    "measured_at",
)
TAU_MEASUREMENT_ARTIFACT_FIELDS = (
    "pair_id",
    "candidate_artifact_hash",
    "domain_policy_id",
    "snapshot_id",
    "snapshot_digest",
    "snapshot_state",
    "corpus_version",
    "candidate",
    "neighbor",
    "neighbors",
    "measurement",
)


def tau_measurement_artifact_digest(row: Mapping[str, object]) -> str:
    contract = {field: row.get(field) for field in TAU_MEASUREMENT_ARTIFACT_FIELDS}
    return sha256_hex(canonical_json(contract))


def qualify_tau_measurement_pair(
    row: Mapping[str, object],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
) -> dict[str, Any]:
    if row.get("synthetic") is True:
        raise ValueError("synthetic pairs cannot count")
    source_class = row.get("source_class")
    if isinstance(source_class, str) and source_class.strip() in BLOCKED_TAU_SOURCE_CLASSES:
        if source_class.strip() in {"requirement_card", "unapproved"}:
            raise ValueError("unapproved corpus rows cannot count")
        raise ValueError("synthetic pairs cannot count")

    pair_id = _required_string(row, "pair_id")
    policy_id = _required_string(row, "domain_policy_id")
    if policy_id not in TAU_MEASUREMENT_POLICIES:
        raise ValueError("tau review uses finance/1 and optimization/1 policies")
    snapshot_state = _required_string(row, "snapshot_state")
    if snapshot_state not in {"calibration", "production_valid"}:
        raise ValueError("tau review requires calibration or production_valid snapshots")
    measurement_artifact_digest = _required_sha256(row, "measurement_artifact_digest")
    if tau_measurement_artifact_digest(row) != measurement_artifact_digest:
        raise ValueError("measurement artifact digest does not match row")
    if measurement_artifact_digest not in trusted_measurement_digests:
        raise ValueError("measurement artifact is not trusted persisted grounding")

    candidate_hash = _required_sha256(row, "candidate_artifact_hash")
    snapshot_id = _required_sha256(row, "snapshot_id")
    snapshot_digest = _required_sha256(row, "snapshot_digest")
    if snapshot_digest != snapshot_id:
        raise ValueError("snapshot_digest must match snapshot_id")
    corpus_version = row.get("corpus_version")
    if (
        isinstance(corpus_version, bool)
        or not isinstance(corpus_version, int)
        or corpus_version < 1
    ):
        raise ValueError("corpus_version must be a positive integer")

    candidate = _require_candidate(row, candidate_hash=candidate_hash)
    neighbors = _require_neighbors(
        row.get("neighbors"),
        policy_id=policy_id,
        approved_projection_digests=approved_projection_digests,
    )
    closest = _required_mapping(row, "neighbor")
    for field in ("record_id", "source_id", "source_paper_id", "text_digest"):
        if _required_string(closest, field) != neighbors[0][field]:
            raise ValueError("designated neighbor must match the closest exported neighbor")

    measurement = _require_measurement(row, neighbors=neighbors)
    return {
        "pair_id": pair_id,
        "candidate_artifact_hash": candidate_hash,
        "domain_policy_id": policy_id,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
        "snapshot_state": snapshot_state,
        "corpus_version": corpus_version,
        "candidate": candidate,
        "neighbor": closest,
        "neighbors": neighbors,
        "measurement": measurement,
        "measurement_artifact_digest": measurement_artifact_digest,
    }


def build_tau_measurement_export_row(
    row: Mapping[str, object],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
) -> dict[str, Any]:
    return qualify_tau_measurement_pair(
        row,
        approved_projection_digests=approved_projection_digests,
        trusted_measurement_digests=trusted_measurement_digests,
    )


def export_tau_measurements_jsonl(
    rows: Sequence[Mapping[str, object]],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
) -> bytes:
    exported = [
        build_tau_measurement_export_row(
            row,
            approved_projection_digests=approved_projection_digests,
            trusted_measurement_digests=trusted_measurement_digests,
        )
        for row in rows
    ]
    candidate_keys = [
        (str(row["domain_policy_id"]), str(row["candidate_artifact_hash"])) for row in exported
    ]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise ValueError("duplicate candidate artifact hash")
    pair_ids = [str(row["pair_id"]) for row in exported]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("duplicate pair_id")
    ordered = sorted(
        exported,
        key=lambda row: (str(row["domain_policy_id"]), str(row["candidate_artifact_hash"])),
    )
    lines = [canonical_json(row).decode("utf-8") for row in ordered]
    return ("\n".join(lines) + "\n").encode("utf-8")


def tau_measurement_export_digest(
    rows: Sequence[Mapping[str, object]],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
) -> str:
    return sha256_hex(
        export_tau_measurements_jsonl(
            rows,
            approved_projection_digests=approved_projection_digests,
            trusted_measurement_digests=trusted_measurement_digests,
        )
    )


def _require_candidate(
    row: Mapping[str, object],
    *,
    candidate_hash: str,
) -> dict[str, object]:
    candidate = _required_mapping(row, "candidate")
    if _required_sha256(candidate, "artifact_hash") != candidate_hash:
        raise ValueError("candidate artifact hash does not match export row")
    paraphrase = normalize_paraphrase(_required_string(candidate, "paraphrase"))
    text_digest = _required_sha256(candidate, "text_digest")
    if sha256_hex(paraphrase.encode("utf-8")) != text_digest:
        raise ValueError("candidate text_digest does not match paraphrase")
    return {
        "artifact_hash": candidate_hash,
        "paraphrase": paraphrase,
        "text_digest": text_digest,
    }


def _require_neighbors(
    value: object,
    *,
    policy_id: str,
    approved_projection_digests: frozenset[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != NOVELTY_K:
        raise ValueError("neighbors must contain exactly 5 unique records")
    neighbors: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("neighbors must contain exactly 5 unique records")
        neighbor = _mapping_with_string_keys(item, "neighbor")
        record_id = _required_string(neighbor, "record_id")
        source_id = normalize_source(_required_string(neighbor, "source_id"))
        source_paper_id = _required_string(neighbor, "source_paper_id")
        text_digest = _required_sha256(neighbor, "text_digest")
        neighbor_policy = _required_string(neighbor, "domain_policy_id")
        if neighbor_policy != policy_id:
            raise ValueError("neighbors must belong to the same policy-bound snapshot")
        distance = _required_finite_number(neighbor, "distance")
        if distance < 0:
            raise ValueError("neighbor distance must be a finite number")
        rank = neighbor.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank != index:
            raise ValueError("neighbor ranks must be 1..k in closest-first order")
        if record_id in record_ids:
            raise ValueError("neighbors must contain exactly 5 unique records")
        record_ids.add(record_id)

        if _required_string(neighbor, "projector_version") != PROJECTOR_VERSION:
            raise ValueError("neighbor projector_version is unsupported")
        projection = _required_mapping(neighbor, "reviewed_projection")
        projection_digest = _required_sha256(neighbor, "reviewed_projection_digest")
        if canonical_reviewed_projection_digest(projection) != projection_digest:
            raise ValueError("neighbor reviewed projection digest does not match projection")
        if projection_digest not in approved_projection_digests:
            raise ValueError("neighbor is not an approved projection")
        if _required_string(projection, "review_status") != "approved":
            raise ValueError("neighbor reviewed projection must be approved")
        _required_string(projection, "human_reviewer")
        _required_utc_timestamp(projection, "human_approved_at")
        if _required_string(projection, "domain_policy_id") != policy_id:
            raise ValueError("neighbor reviewed projection policy does not match")
        if _required_string(projection, "source_paper_id") != source_paper_id:
            raise ValueError("neighbor source_paper_id does not match reviewed projection")
        projection_source = projection.get("source")
        if projection_source is None:
            expected_source = normalize_source(f"paper:{source_paper_id}")
        elif isinstance(projection_source, str) and projection_source.strip():
            expected_source = normalize_source(projection_source)
        else:
            raise ValueError("neighbor reviewed projection source is invalid")
        if expected_source != source_id:
            raise ValueError("neighbor source_id does not match reviewed projection")
        if _required_sha256(projection, "paraphrase_sha256") != text_digest:
            raise ValueError("neighbor text_digest does not match reviewed projection")

        neighbors.append(
            {
                "record_id": record_id,
                "source_id": source_id,
                "source_paper_id": source_paper_id,
                "domain_policy_id": neighbor_policy,
                "text_digest": text_digest,
                "projector_version": PROJECTOR_VERSION,
                "reviewed_projection_digest": projection_digest,
                "reviewed_projection": projection,
                "distance": distance,
                "rank": rank,
            }
        )
    ordered = sorted(neighbors, key=lambda item: (item["distance"], item["record_id"]))
    if [item["record_id"] for item in ordered] != [item["record_id"] for item in neighbors]:
        raise ValueError("neighbors must be ordered closest first")
    return neighbors


def _require_measurement(
    row: Mapping[str, object],
    *,
    neighbors: list[dict[str, Any]],
) -> dict[str, object]:
    measurement = _required_mapping(row, "measurement")
    if measurement.get("k") != NOVELTY_K:
        raise ValueError("measurement k must match novelty k")
    distances = [float(item["distance"]) for item in neighbors]
    raw_distances = measurement.get("distances")
    if not isinstance(raw_distances, list) or len(raw_distances) != NOVELTY_K:
        raise ValueError("measurement distances must match neighbors")
    measured_distances = [_finite_number(item, "measurement distance") for item in raw_distances]
    if measured_distances != distances:
        raise ValueError("measurement distances must match neighbors")
    mean = mean_cosine_distance(distances)
    if mean is None:
        raise ValueError("neighbor distances are required")
    evidence = _required_finite_number(measurement, "evidence_mean_distance")
    if evidence < 0 or evidence != mean:
        raise ValueError("exported mean does not match neighbor distances")

    model_id = _required_string(measurement, "embedding_model_id")
    model_version = _required_string(measurement, "embedding_model_version")
    dimension = measurement.get("embedding_dimension")
    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1:
        raise ValueError("embedding_dimension must be a positive integer")
    normalization = _required_string(measurement, "normalization_policy")
    if _required_string(measurement, "distance_metric") != "cosine_distance":
        raise ValueError("distance_metric must be cosine_distance")
    contract_version = _required_string(measurement, "algorithm_contract_version")
    measured_at = _required_utc_timestamp(measurement, "measured_at")
    return {
        "evidence_mean_distance": mean,
        "k": NOVELTY_K,
        "distances": distances,
        "embedding_model_id": model_id,
        "embedding_model_version": model_version,
        "embedding_dimension": dimension,
        "normalization_policy": normalization,
        "distance_metric": "cosine_distance",
        "algorithm_contract_version": contract_version,
        "measured_at": measured_at,
    }


def _required_mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{key} is required")
    return _mapping_with_string_keys(item, key)


def _mapping_with_string_keys(value: Mapping[Any, object], label: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} keys must be strings")
        result[key] = item
    return result


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} is required")
    return item.strip()


def _required_sha256(value: Mapping[str, object], key: str) -> str:
    digest = _required_string(value, key)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{key} must be a lowercase SHA-256 hex digest")
    return digest


def _required_finite_number(value: Mapping[str, object], key: str) -> float:
    return _finite_number(value.get(key), key)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _required_utc_timestamp(value: Mapping[str, object], key: str) -> str:
    timestamp = _required_string(value, key)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{key} must be a UTC timestamp")
    return timestamp
