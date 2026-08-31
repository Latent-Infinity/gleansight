from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nsqd.domain.ablation import calendar_month_cutoff, calendar_month_window
from nsqd.domain.diverge import select_target_cell
from nsqd.domain.status import cell_status, record_lifecycle, status_window

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
WINDOW_CHOICES_DAYS = (365, 730, 1095)
CAL = {
    "as_of": AS_OF,
    "snapshot_state": "calibration",
    "inspected": True,
    "expected": False,
}


def _paper(days_ago: int) -> dict[str, object]:
    return {"type": "paper", "harvested_at": AS_OF - timedelta(days=days_ago)}


def _code(days_ago: int) -> dict[str, object]:
    return {"type": "code", "harvested_at": AS_OF - timedelta(days=days_ago)}


def test_twelve_twenty_four_thirty_six_day_windows_shift_current_and_active() -> None:
    ages = (364, 365, 400, 729, 730, 731, 800, 1094, 1095, 1096)
    current = {
        days: {
            age: record_lifecycle(_paper(age), as_of=AS_OF, window=status_window(days)) == "current"
            for age in ages
        }
        for days in WINDOW_CHOICES_DAYS
    }
    assert current[365][364] is True
    assert current[365][365] is True
    assert current[365][400] is False
    assert current[730][400] is True
    assert current[730][730] is True
    assert current[730][731] is False
    assert current[1095][800] is True
    assert current[1095][1095] is True
    assert current[1095][1096] is False

    dense_400 = [_paper(400), _paper(400), _code(400)]
    dense_800 = [_paper(800), _paper(800), _code(800)]
    statuses_400 = {
        days: cell_status(dense_400, window=status_window(days), **CAL)
        for days in WINDOW_CHOICES_DAYS
    }
    statuses_800 = {
        days: cell_status(dense_800, window=status_window(days), **CAL)
        for days in WINDOW_CHOICES_DAYS
    }
    assert statuses_400 == {365: "Unknown", 730: "Active", 1095: "Active"}
    assert statuses_800 == {365: "Unknown", 730: "Unknown", 1095: "Active"}

    targets = {
        days: select_target_cell(
            {
                "a": statuses_400[days],
                "b": statuses_800[days],
                "c": "Missing",
            }
        )
        for days in WINDOW_CHOICES_DAYS
    }
    assert targets[365] == "c"
    assert targets[730] == "c"
    assert targets[1095] == "c"


def test_keep_730_day_default_after_window_length_probe() -> None:
    from nsqd.domain.status import STATUS_WINDOW_DAYS

    assert STATUS_WINDOW_DAYS == 730
    assert WINDOW_CHOICES_DAYS[1] == STATUS_WINDOW_DAYS


@pytest.mark.parametrize(
    ("as_of", "months", "expected"),
    [
        (
            datetime(2024, 3, 31, 15, 30, tzinfo=UTC),
            1,
            datetime(2024, 2, 29, 15, 30, tzinfo=UTC),
        ),
        (
            datetime(2023, 3, 31, 15, 30, tzinfo=UTC),
            1,
            datetime(2023, 2, 28, 15, 30, tzinfo=UTC),
        ),
        (
            datetime(2024, 2, 29, 15, 30, tzinfo=UTC),
            12,
            datetime(2023, 2, 28, 15, 30, tzinfo=UTC),
        ),
        (
            datetime(2024, 1, 31, 15, 30, tzinfo=UTC),
            1,
            datetime(2023, 12, 31, 15, 30, tzinfo=UTC),
        ),
    ],
)
def test_calendar_month_cutoff_clamps_month_end_in_utc(
    as_of: datetime,
    months: int,
    expected: datetime,
) -> None:
    assert calendar_month_cutoff(as_of, months=months) == expected


def test_calendar_month_window_is_report_only_and_differs_at_leap_boundary() -> None:
    as_of = datetime(2024, 3, 31, tzinfo=UTC)
    boundary_record = {"type": "paper", "harvested_at": datetime(2022, 3, 31, tzinfo=UTC)}

    assert record_lifecycle(boundary_record, as_of=as_of, window=status_window()) == "stale"
    assert (
        record_lifecycle(boundary_record, as_of=as_of, window=calendar_month_window(as_of))
        == "current"
    )


@pytest.mark.parametrize(
    ("as_of", "months"),
    [
        (datetime(2024, 3, 31), 24),
        (datetime(2024, 3, 31, tzinfo=UTC), 0),
        (datetime(2024, 3, 31, tzinfo=UTC), True),
    ],
)
def test_calendar_month_cutoff_rejects_invalid_report_inputs(
    as_of: datetime,
    months: object,
) -> None:
    with pytest.raises(ValueError):
        calendar_month_cutoff(as_of, months=months)
