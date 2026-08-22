from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

GroundingClass = Literal[
    "already_done",
    "renamed",
    "related_partial",
    "orthogonal",
    "clean_gap",
    "unevaluated",
]


@dataclass(frozen=True)
class LayerResult:
    layer: int
    checked: str
    hit: bool
    escalate_reason: str | None
    grounding_class: GroundingClass | None
    confidence: float | None


def classify_local(
    *,
    exact_source_hit: bool,
    terminology_hit: bool,
    evidence: float | None,
    code_or_benchmark_hit: bool,
) -> tuple[GroundingClass, float, list[LayerResult]]:
    layers: list[LayerResult] = []
    if exact_source_hit:
        layers.append(LayerResult(1, "exact source/DOI/title", True, None, "already_done", 1.0))
        return "already_done", 1.0, layers
    layers.append(LayerResult(1, "exact source/DOI/title", False, "no exact identity", None, None))
    if terminology_hit:
        layers.append(LayerResult(2, "terminology variants", True, None, "renamed", 0.8))
        return "renamed", 0.8, layers
    layers.append(LayerResult(2, "terminology variants", False, "no variant hit", None, None))
    if evidence is None:
        layers.append(LayerResult(3, "embedding k-NN", False, "evidence undefined", None, None))
    elif evidence < 0.15:
        layers.append(LayerResult(3, "embedding k-NN", True, None, "related_partial", 0.6))
        return "related_partial", 0.6, layers
    else:
        layers.append(LayerResult(3, "embedding k-NN", True, None, "orthogonal", 0.5))
        return "orthogonal", 0.5, layers
    if code_or_benchmark_hit:
        layers.append(LayerResult(4, "code/benchmark", True, None, "already_done", 0.9))
        return "already_done", 0.9, layers
    layers.append(LayerResult(4, "code/benchmark", False, "no neighbor", None, None))
    return "unevaluated", 0.0, layers


LIVE_SEARCH_BUDGET = 3
LIVE_PRIOR_ART_CONFIDENCE = 0.4


def live_escalation_allowed(*, snapshot_state: str, local_class: GroundingClass) -> bool:
    return snapshot_state in {"calibration", "production_valid"} and local_class == "unevaluated"


def apply_live_hits(
    *,
    local_class: GroundingClass,
    local_confidence: float,
    live_hits: list[dict[str, Any]],
) -> tuple[GroundingClass, float]:
    if local_class != "unevaluated" or not live_hits:
        return local_class, local_confidence
    return "related_partial", LIVE_PRIOR_ART_CONFIDENCE
