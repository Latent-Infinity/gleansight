from __future__ import annotations

from typing import Literal

from nsqd.domain.grounding import GroundingClass

SnapshotState = Literal["smoke_only", "calibration", "production_valid"]


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
    if evidence < 0.15:
        return 1
    if evidence < 0.30:
        return 2
    if evidence < 0.45:
        return 3
    if evidence < 0.60:
        return 4
    return 5


def mean_cosine_distance(distances: list[float]) -> float | None:
    if not distances:
        return None
    return sum(distances) / len(distances)
