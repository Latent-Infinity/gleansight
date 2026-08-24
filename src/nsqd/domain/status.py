from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal, cast, get_args

from nsqd.domain.novelty import require_snapshot_state
from nsqd.domain.policy import get_policy, records_for_policy
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
CELL_STATUS_VALUES = frozenset(get_args(CellStatus))


def _require_utc_as_of(as_of: datetime) -> None:
    if not is_utc_datetime(as_of):
        raise ValueError("as_of must be a UTC datetime")


def require_cell_status(value: object) -> CellStatus:
    if not isinstance(value, str) or value not in CELL_STATUS_VALUES:
        raise ValueError("invalid CellStatus value")
    return cast(CellStatus, value)


def _require_cells_within_universe(
    name: str,
    cell_ids: frozenset[str] | set[str],
    *,
    universe: frozenset[str],
) -> None:
    if not cell_ids <= universe:
        raise ValueError(f"{name} must stay inside the selected policy universe")


def _require_reason_cells_within_universe(
    invalid_reasons: dict[str, str], *, universe: frozenset[str]
) -> None:
    if not set(invalid_reasons) <= universe:
        raise ValueError("cell_invalid_reasons keys must stay inside the selected policy universe")


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
    if record.get("invalid_reason") or record.get("retracted") is True:
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
    density_cut: int = 3,
) -> CellStatus:
    _require_utc_as_of(as_of)
    require_snapshot_state(snapshot_state)
    if density_cut < 2:
        raise ValueError("density_cut must be >= 2")
    if snapshot_state == "smoke_only":
        return "Unknown"
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
    if disagreement or (total == 0 and not inspected):
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
    if total >= density_cut and recent:
        return "Active"
    if 1 <= total < density_cut:
        return "Sparse"
    if total >= density_cut:
        return "Unknown"
    return "Unknown"


def status_table(
    records: list[dict[str, Any]],
    *,
    domain_policy_id: str,
    as_of: datetime,
    snapshot_state: str,
    inspected_cell_ids: frozenset[str] | set[str] = frozenset(),
    expected_cell_ids: frozenset[str] | set[str] | None = None,
    cell_invalid_reasons: dict[str, str] | None = None,
    disagreement_cell_ids: frozenset[str] | set[str] = frozenset(),
    window: timedelta = timedelta(days=365 * 2),
) -> dict[str, CellStatus]:
    if not isinstance(domain_policy_id, str) or not domain_policy_id.strip():
        raise ValueError("domain_policy_id is required")
    _require_utc_as_of(as_of)
    policy = get_policy(domain_policy_id.strip())
    universe = policy.universe()
    require_snapshot_state(snapshot_state)
    expected = policy.expected_cells if expected_cell_ids is None else frozenset(expected_cell_ids)
    invalid_reasons = cell_invalid_reasons or {}
    inspected_ids = frozenset(inspected_cell_ids)
    disagreement_ids = frozenset(disagreement_cell_ids)
    _require_cells_within_universe(
        "expected_cell_ids",
        expected,
        universe=universe,
    )
    _require_cells_within_universe(
        "inspected_cell_ids",
        inspected_ids,
        universe=universe,
    )
    _require_cells_within_universe(
        "disagreement_cell_ids",
        disagreement_ids,
        universe=universe,
    )
    _require_reason_cells_within_universe(invalid_reasons, universe=universe)
    grouped: dict[str, list[dict[str, Any]]] = {cell_id: [] for cell_id in universe}
    for row in records_for_policy(records, policy.policy_id):
        coords = row.get("coordinates")
        if not isinstance(coords, dict):
            coords = row.get("research_descriptor")
        if not isinstance(coords, dict):
            continue
        try:
            cell_id = policy.cell_id(coords)
        except ValueError:
            continue
        bucket = grouped.get(cell_id)
        if bucket is not None:
            bucket.append(row)
    table: dict[str, CellStatus] = {}
    for cell_id, cell_records in grouped.items():
        table[cell_id] = cell_status(
            cell_records,
            as_of=as_of,
            snapshot_state=snapshot_state,
            inspected=cell_id in expected or cell_id in inspected_ids,
            expected=cell_id in expected,
            invalid_reason=invalid_reasons.get(cell_id),
            disagreement=cell_id in disagreement_ids,
            method_claims_evaluation=any(
                record.get("method_claims_evaluation") is True for record in cell_records
            ),
            window=window,
        )
    return table
