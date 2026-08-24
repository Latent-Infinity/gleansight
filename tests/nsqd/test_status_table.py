from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nsqd.domain.policy import FINANCE_POLICY, OPTIMIZATION_POLICY, UnknownDomainPolicy
from nsqd.domain.status import cell_status, status_table

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
RECENT = AS_OF - timedelta(days=10)
STALE = AS_OF - timedelta(days=365 * 3)
FINANCE_CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"
FINANCE_OTHER = "mechanism=behavioral|target=returns|horizon=daily"
OPT_CELL = "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"
FINANCE_COORDS = {
    "mechanism": "flow-driven",
    "target": "drawdown",
    "horizon": "intraday",
}
FINANCE_OTHER_COORDS = {
    "mechanism": "behavioral",
    "target": "returns",
    "horizon": "daily",
}
OPT_COORDS = {
    "problem": "constrained-expectation",
    "method": "sequential-quadratic",
    "setting": "rank-deficient",
}


def _rec(
    rec_type: str,
    harvested: datetime | None = None,
    *,
    domain_policy_id: str,
    coordinates: dict[str, str],
    tags: list[str] | None = None,
    invalid: str | None = None,
    claims_evaluation: bool = False,
) -> dict[str, object]:
    row: dict[str, object] = {
        "type": rec_type,
        "domain_policy_id": domain_policy_id,
        "coordinates": coordinates,
    }
    if harvested is not None:
        row["harvested_at"] = harvested
    if tags is not None:
        row["tags"] = tags
    if invalid is not None:
        row["invalid_reason"] = invalid
    if claims_evaluation:
        row["method_claims_evaluation"] = True
    return row


def test_status_table_covers_finance_universe_on_empty_snapshot() -> None:
    table = status_table(
        [],
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="calibration",
    )
    assert len(table) == 336
    assert set(table) == FINANCE_POLICY.universe()
    assert table[FINANCE_CELL] == "Missing"
    assert set(table.values()) == {"Missing", "Unknown"}
    assert sum(status == "Missing" for status in table.values()) == 1


def test_status_table_covers_optimization_universe() -> None:
    table = status_table(
        [],
        domain_policy_id="optimization/1",
        as_of=AS_OF,
        snapshot_state="calibration",
    )
    assert len(table) == 8
    assert set(table) == OPTIMIZATION_POLICY.universe()
    assert set(table.values()) == {"Unknown"}


def test_status_table_requires_explicit_policy() -> None:
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        status_table([], domain_policy_id="", as_of=AS_OF, snapshot_state="calibration")
    with pytest.raises(UnknownDomainPolicy, match="unknown domain_policy_id"):
        status_table(
            [],
            domain_policy_id="missing/1",
            as_of=AS_OF,
            snapshot_state="calibration",
        )


def test_status_table_rejects_non_utc_as_of() -> None:
    with pytest.raises(ValueError, match="as_of must be a UTC datetime"):
        status_table(
            [],
            domain_policy_id="finance/1",
            as_of=datetime(2024, 1, 1),
            snapshot_state="calibration",
        )


def test_pack_scoped_table_ignores_other_policy_records() -> None:
    records = [
        _rec("paper", RECENT, domain_policy_id="optimization/1", coordinates=FINANCE_COORDS),
        _rec(
            "paper",
            RECENT,
            domain_policy_id="optimization/1",
            coordinates=OPT_COORDS,
        ),
        _rec("code", RECENT, domain_policy_id="optimization/1", coordinates=OPT_COORDS),
        _rec("benchmark", RECENT, domain_policy_id="optimization/1", coordinates=OPT_COORDS),
    ]
    finance = status_table(
        records,
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="calibration",
    )
    optimization = status_table(
        records,
        domain_policy_id="optimization/1",
        as_of=AS_OF,
        snapshot_state="calibration",
        inspected_cell_ids=frozenset({OPT_CELL}),
        expected_cell_ids=frozenset({OPT_CELL}),
    )
    assert finance[FINANCE_CELL] == "Missing"
    assert set(finance.values()) == {"Missing", "Unknown"}
    assert optimization[OPT_CELL] == "Active"
    assert sum(status != "Unknown" for status in optimization.values()) == 1


def test_unlisted_coordinates_do_not_place_or_leak() -> None:
    records = [
        _rec(
            "paper",
            RECENT,
            domain_policy_id="finance/1",
            coordinates={"mechanism": "not-a-mechanism", "target": "returns", "horizon": "daily"},
        ),
        _rec("paper", RECENT, domain_policy_id="finance/1", coordinates=OPT_COORDS),
    ]
    table = status_table(
        records,
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="calibration",
    )
    assert table[FINANCE_CELL] == "Missing"
    assert set(table.values()) == {"Missing", "Unknown"}
    assert sum(status == "Missing" for status in table.values()) == 1


def test_expected_empty_cell_is_missing_and_uninspected_empty_is_unknown() -> None:
    table = status_table(
        [],
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="calibration",
        inspected_cell_ids=frozenset({FINANCE_OTHER}),
        expected_cell_ids=frozenset({FINANCE_CELL}),
    )
    assert table[FINANCE_CELL] == "Missing"
    assert table[FINANCE_OTHER] == "Unknown"
    assert sum(status == "Missing" for status in table.values()) == 1


def test_larger_snapshot_assigns_exclusive_statuses_per_cell() -> None:
    records = [
        _rec("paper", RECENT, domain_policy_id="finance/1", coordinates=FINANCE_COORDS),
        _rec("code", RECENT, domain_policy_id="finance/1", coordinates=FINANCE_COORDS),
        *[
            _rec(
                "paper",
                RECENT,
                domain_policy_id="finance/1",
                coordinates=FINANCE_OTHER_COORDS,
                claims_evaluation=True,
            )
            for _ in range(6)
        ],
        _rec("code", RECENT, domain_policy_id="finance/1", coordinates=FINANCE_OTHER_COORDS),
        _rec(
            "paper",
            RECENT,
            domain_policy_id="finance/1",
            coordinates={"mechanism": "institutional", "target": "liquidity", "horizon": "weekly"},
            invalid="malformed",
        ),
        _rec(
            "paper",
            STALE,
            domain_policy_id="finance/1",
            coordinates={"mechanism": "reflexivity", "target": "crowding", "horizon": "tick"},
            tags=["stalled"],
        ),
        _rec(
            "paper",
            RECENT,
            domain_policy_id="finance/1",
            coordinates={
                "mechanism": "microstructure",
                "target": "slippage",
                "horizon": "event-time",
            },
            tags=["future_work"],
        ),
        _rec(
            "paper",
            RECENT,
            domain_policy_id="optimization/1",
            coordinates=OPT_COORDS,
        ),
    ]
    stalled_cell = "mechanism=reflexivity|target=crowding|horizon=tick"
    future_cell = "mechanism=microstructure|target=slippage|horizon=event-time"
    invalid_cell = "mechanism=institutional|target=liquidity|horizon=weekly"
    table = status_table(
        records,
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="calibration",
    )
    assert len(table) == 336
    assert table[FINANCE_CELL] == "Sparse"
    assert table[FINANCE_OTHER] == "Benchmark-gap"
    assert table[invalid_cell] == "Invalid"
    assert table[stalled_cell] == "Stalled"
    assert table[future_cell] == "Future-work-only"
    assert table["mechanism=balance-sheet|target=volatility|horizon=regime-time"] == "Unknown"
    assert OPT_CELL not in table


def test_smoke_snapshot_forces_every_cell_unknown() -> None:
    records = [
        _rec("paper", RECENT, domain_policy_id="finance/1", coordinates=FINANCE_COORDS),
        _rec("code", RECENT, domain_policy_id="finance/1", coordinates=FINANCE_COORDS),
        _rec("benchmark", RECENT, domain_policy_id="finance/1", coordinates=FINANCE_COORDS),
    ]
    table = status_table(
        records,
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="smoke_only",
        inspected_cell_ids=frozenset({FINANCE_CELL}),
        expected_cell_ids=frozenset({FINANCE_CELL}),
    )
    assert set(table.values()) == {"Unknown"}


def test_smoke_snapshot_forces_invalid_records_and_cells_unknown() -> None:
    records = [
        _rec(
            "paper",
            RECENT,
            domain_policy_id="finance/1",
            coordinates=FINANCE_COORDS,
            invalid="malformed",
        )
    ]
    table = status_table(
        records,
        domain_policy_id="finance/1",
        as_of=AS_OF,
        snapshot_state="smoke_only",
        expected_cell_ids=frozenset({FINANCE_CELL}),
        cell_invalid_reasons={FINANCE_CELL: "invalid capture"},
    )
    assert (
        cell_status(
            records,
            as_of=AS_OF,
            snapshot_state="smoke_only",
            inspected=True,
            expected=True,
            invalid_reason="invalid capture",
        )
        == "Unknown"
    )
    assert set(table.values()) == {"Unknown"}


def test_status_table_rejects_invalid_snapshot_state() -> None:
    with pytest.raises(ValueError, match="invalid snapshot_state"):
        status_table(
            [],
            domain_policy_id="finance/1",
            as_of=AS_OF,
            snapshot_state="bad-state",
        )


def test_cell_status_rejects_invalid_snapshot_state() -> None:
    with pytest.raises(ValueError, match="invalid snapshot_state"):
        cell_status(
            [],
            as_of=AS_OF,
            snapshot_state="bad-state",
            inspected=False,
            expected=False,
        )


def test_status_table_rejects_expected_cells_outside_policy_universe() -> None:
    with pytest.raises(
        ValueError, match="expected_cell_ids must stay inside the selected policy universe"
    ):
        status_table(
            [],
            domain_policy_id="finance/1",
            as_of=AS_OF,
            snapshot_state="calibration",
            expected_cell_ids=frozenset({OPT_CELL}),
        )


def test_status_table_rejects_inspected_cells_outside_policy_universe() -> None:
    with pytest.raises(
        ValueError, match="inspected_cell_ids must stay inside the selected policy universe"
    ):
        status_table(
            [],
            domain_policy_id="finance/1",
            as_of=AS_OF,
            snapshot_state="calibration",
            inspected_cell_ids=frozenset({OPT_CELL}),
        )


def test_status_table_rejects_disagreement_cells_outside_policy_universe() -> None:
    with pytest.raises(
        ValueError, match="disagreement_cell_ids must stay inside the selected policy universe"
    ):
        status_table(
            [],
            domain_policy_id="finance/1",
            as_of=AS_OF,
            snapshot_state="calibration",
            disagreement_cell_ids=frozenset({OPT_CELL}),
        )


def test_status_table_rejects_invalid_reason_cells_outside_policy_universe() -> None:
    with pytest.raises(
        ValueError, match="cell_invalid_reasons keys must stay inside the selected policy universe"
    ):
        status_table(
            [],
            domain_policy_id="finance/1",
            as_of=AS_OF,
            snapshot_state="calibration",
            cell_invalid_reasons={OPT_CELL: "bad"},
        )
