from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from nsqd.domain.snapshot import is_utc_datetime

CellStatus = Literal[
    "Invalid",
    "Unknown",
    "Future-work-only",
    "Stalled",
    "Missing",
    "Code-gap",
    "Benchmark-gap",
    "Mature",
    "Active",
    "Sparse",
]

RecordLifecycle = Literal["invalid", "future_work", "attempted", "current", "stale"]


def _require_utc_as_of(as_of: datetime) -> None:
    if not is_utc_datetime(as_of):
        raise ValueError("as_of must be a UTC datetime")


def _is_current_harvest(*, harvested: object, as_of: datetime, window: timedelta) -> bool:
    if isinstance(harvested, str):
        try:
            harvested = datetime.fromisoformat(harvested.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(harvested, datetime):
        return False
    return is_utc_datetime(harvested) and harvested >= as_of - window


def record_lifecycle(
    record: dict[str, Any],
    *,
    as_of: datetime,
    window: timedelta = timedelta(days=365 * 2),
) -> RecordLifecycle:
    _require_utc_as_of(as_of)
    if record.get("invalid_reason"):
        return "invalid"
    tags = set(record.get("tags") or [])
    if "future_work" in tags:
        return "future_work"
    if "stalled" in tags or "abandoned" in tags:
        return "attempted"
    harvested = record.get("harvested_at")
    rec_type = record.get("type")
    if rec_type in {"paper", "code"} and _is_current_harvest(
        harvested=harvested, as_of=as_of, window=window
    ):
        return "current"
    return "stale"


def cell_status(
    records: list[dict[str, Any]],
    *,
    as_of: datetime,
    snapshot_state: str,
    inspected: bool,
    expected: bool,
    invalid_reason: str | None = None,
    disagreement: bool = False,
    method_claims_evaluation: bool = False,
    window: timedelta = timedelta(days=365 * 2),
) -> CellStatus:
    _require_utc_as_of(as_of)
    lifecycles = [record_lifecycle(record, as_of=as_of, window=window) for record in records]
    valid = [
        (record, life)
        for record, life in zip(records, lifecycles, strict=True)
        if life != "invalid"
    ]
    p = sum(1 for record, _ in valid if record.get("type") == "paper")
    c = sum(1 for record, _ in valid if record.get("type") == "code")
    b = sum(1 for record, _ in valid if record.get("type") == "benchmark")
    total = p + c + b
    attempted = sum(1 for _, life in valid if life == "attempted")
    current_paper = sum(
        1 for record, life in valid if life == "current" and record.get("type") == "paper"
    )
    current_code = sum(
        1 for record, life in valid if life == "current" and record.get("type") == "code"
    )

    if invalid_reason or any(life == "invalid" for life in lifecycles):
        return "Invalid"
    if disagreement or snapshot_state == "smoke_only" or (total == 0 and not inspected):
        return "Unknown"
    if total >= 1 and all(life == "future_work" for _, life in valid):
        return "Future-work-only"
    if attempted >= 1 and current_paper == 0 and current_code == 0:
        return "Stalled"
    if inspected and expected and total == 0:
        return "Missing"
    if p >= 1 and c == 0:
        return "Code-gap"
    if (p + c) >= 1 and b == 0 and method_claims_evaluation:
        return "Benchmark-gap"
    if p >= 5 and c >= 1:
        return "Mature"
    recent = any(
        _is_current_harvest(harvested=record.get("harvested_at"), as_of=as_of, window=window)
        for record, _ in valid
    )
    if total >= 3 and recent:
        return "Active"
    if 1 <= total < 3:
        return "Sparse"
    if total >= 3:
        return "Unknown"
    return "Unknown"
