from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import NotRequired, TypedDict


class CellStatusOptions(TypedDict):
    snapshot_state: str
    inspected: bool
    expected: bool
    invalid_reason: NotRequired[str | None]
    disagreement: NotRequired[bool]
    method_claims_evaluation: NotRequired[bool]


class TimedCellStatusOptions(CellStatusOptions):
    as_of: datetime


class AcquisitionCycleOptions(TypedDict):
    snapshot_id: str
    domain_policy_id: str
    failure_signature: tuple[str, ...] | list[str]
    rendered_query: str
    filters: dict[str, object]


def numeric_distance(row: Mapping[str, object]) -> float:
    distance = row["distance"]
    assert isinstance(distance, (int, float))
    return float(distance)
