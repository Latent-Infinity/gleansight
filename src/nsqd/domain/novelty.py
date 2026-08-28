from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from nsqd.domain.grounding import GroundingClass

SnapshotState = Literal["smoke_only", "calibration", "production_valid"]
NOVELTY_THRESHOLD_TAU: float | None = None
NOVELTY_BIN_EDGES = (0.15, 0.30, 0.45, 0.60)
NOVELTY_K = 5
UNSET_TAU_SEMANTICS = "unset_report_only"


def require_snapshot_state(snapshot_state: str) -> SnapshotState:
    if snapshot_state == "smoke_only":
        return "smoke_only"
    if snapshot_state == "calibration":
        return "calibration"
    if snapshot_state == "production_valid":
        return "production_valid"
    raise ValueError(
        "invalid snapshot_state: expected one of smoke_only, calibration, production_valid"
    )


def novelty_term(
    *,
    evidence: float | None,
    snapshot_state: SnapshotState,
    grounding_class: GroundingClass,
) -> int:
    if grounding_class in {"already_done", "renamed"}:
        return 0
    if snapshot_state not in {"calibration", "production_valid"}:
        return 0
    if evidence is None:
        return 0
    if evidence < NOVELTY_BIN_EDGES[0]:
        return 1
    if evidence < NOVELTY_BIN_EDGES[1]:
        return 2
    if evidence < NOVELTY_BIN_EDGES[2]:
        return 3
    if evidence < NOVELTY_BIN_EDGES[3]:
        return 4
    return 5


def apply_novelty_threshold(
    term: int,
    *,
    evidence: float | None,
    tau: float | None = NOVELTY_THRESHOLD_TAU,
) -> int:
    if tau is None:
        return term
    if isinstance(tau, bool) or not isinstance(tau, (int, float)):
        raise ValueError("tau must be a non-negative number or unset")
    normalized_tau = float(tau)
    if not math.isfinite(normalized_tau) or normalized_tau < 0:
        raise ValueError("tau must be a non-negative number or unset")
    if evidence is not None and evidence < normalized_tau:
        return 0
    return term


def mean_cosine_distance(distances: list[float]) -> float | None:
    if not distances:
        return None
    return sum(distances) / len(distances)


def k_nn_evidence(distances: Sequence[float], k: int) -> float | None:
    if k < 1:
        raise ValueError("k must be >= 1")
    return mean_cosine_distance(list(distances[:k]))


def spearman_rho(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("spearman_rho length mismatch")
    if len(left) < 2:
        raise ValueError("spearman_rho needs at least 2 items")
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    return _pearson(left_ranks, right_ranks)


def novelty_rank_spearman(
    *,
    item_distances: Mapping[str, Sequence[float]],
    k_values: Sequence[int],
    baseline_k: int,
    snapshot_state: str,
) -> dict[int, float]:
    state = require_snapshot_state(snapshot_state)
    if state == "smoke_only":
        raise ValueError("ALG.K requires a calibration or production_valid snapshot")
    item_ids = sorted(item_distances)
    if len(item_ids) < 2:
        raise ValueError("novelty_rank_spearman needs at least 2 items")
    baseline = [
        _require_k_nn_evidence(item_id, item_distances[item_id], baseline_k) for item_id in item_ids
    ]
    correlations: dict[int, float] = {}
    for k_value in k_values:
        series = [
            _require_k_nn_evidence(item_id, item_distances[item_id], k_value)
            for item_id in item_ids
        ]
        correlations[int(k_value)] = spearman_rho(series, baseline)
    return correlations


def _require_k_nn_evidence(item_id: str, distances: Sequence[float], k: int) -> float:
    if len(distances) < k:
        raise ValueError(f"novelty rank evidence needs at least {k} distances for {item_id}")
    evidence = k_nn_evidence(distances, k)
    if evidence is None:
        raise ValueError(f"novelty rank evidence is missing for {item_id}")
    return evidence


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        average = (start + end) / 2.0 + 1.0
        for position in range(start, end + 1):
            ranks[order[position]] = average
        start = end + 1
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    count = len(left)
    mean_left = sum(left) / count
    mean_right = sum(right) / count
    numerator = sum(
        (left_value - mean_left) * (right_value - mean_right)
        for left_value, right_value in zip(left, right, strict=True)
    )
    denom_left = math.sqrt(sum((value - mean_left) ** 2 for value in left))
    denom_right = math.sqrt(sum((value - mean_right) ** 2 for value in right))
    if denom_left == 0.0 or denom_right == 0.0:
        raise ValueError("spearman_rho is undefined for constant ranks")
    return numerator / (denom_left * denom_right)
