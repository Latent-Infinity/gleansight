from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.screens.archive import ArchiveScreen
from papers.ui.screens.card import CardScreen
from papers.ui.screens.map import MapScreen


@dataclass
class _Services:
    map_snapshot: object = None
    list_archive_elites: object = None
    get_frontier_card: object = None


def _click(button: ft.Button) -> None:
    assert button.on_click is not None
    with patch.object(ft.Control, "update", return_value=None):
        button.on_click(MagicMock())


def test_map_screen_loads_and_renders_cell_statuses() -> None:
    calls: list[dict[str, object]] = []

    def map_snapshot(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "cell_statuses": {"mechanism=flow-driven|target=drawdown|horizon=intraday": "Unknown"},
        }

    screen = MapScreen(_Services(map_snapshot=map_snapshot)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    snapshot_input, _policy_input, _state_input, load = row.controls
    assert isinstance(snapshot_input, ft.TextField)
    assert isinstance(load, ft.Button)
    snapshot_input.value = "snap"

    _click(load)

    assert calls == [
        {
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "snapshot_state": "calibration",
        }
    ]
    output = screen.controls[3]
    assert isinstance(output, ft.Text)
    assert '"Unknown": 1' in str(output.value)


def test_map_screen_reports_validation_and_service_errors() -> None:
    def fail(**_kwargs: object) -> dict[str, object]:
        raise ValueError("unknown snapshot_id")

    screen = MapScreen(_Services(map_snapshot=fail)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    snapshot_input, _policy_input, _state_input, load = row.controls
    assert isinstance(snapshot_input, ft.TextField)
    assert isinstance(load, ft.Button)
    output = screen.controls[3]
    assert isinstance(output, ft.Text)

    _click(load)
    assert output.value == "Snapshot id is required."

    snapshot_input.value = "missing"
    _click(load)
    assert output.value == "Error: unknown snapshot_id"


def test_archive_screen_refreshes_elites_and_empty_state() -> None:
    rows = [
        {
            "card_id": "c1",
            "cell_id": "mechanism=flow-driven|target=drawdown|horizon=intraday",
            "title": "elite",
            "viability": 5,
        }
    ]
    screen = ArchiveScreen(_Services(list_archive_elites=lambda: list(rows))).build()
    assert isinstance(screen, ft.Column)
    refresh = screen.controls[2]
    status = screen.controls[3]
    output = screen.controls[4]
    assert isinstance(refresh, ft.Button)
    assert isinstance(status, ft.Text)
    assert isinstance(output, ft.ListView)

    _click(refresh)
    assert status.value == "1 elite card(s)"
    assert len(output.controls) == 1
    assert "elite" in str(output.controls[0].value)

    rows.clear()
    _click(refresh)
    assert status.value == "No elite cards."
    assert output.controls == []


def test_archive_screen_reports_service_error() -> None:
    def fail() -> list[dict[str, object]]:
        raise RuntimeError("database unavailable")

    screen = ArchiveScreen(_Services(list_archive_elites=fail)).build()
    assert isinstance(screen, ft.Column)
    refresh = screen.controls[2]
    status = screen.controls[3]
    assert isinstance(refresh, ft.Button)
    assert isinstance(status, ft.Text)

    _click(refresh)

    assert status.value == "Error: database unavailable"


def test_card_screen_validates_and_renders_card() -> None:
    calls: list[str] = []

    def get_frontier_card(card_id: str) -> dict[str, object] | None:
        calls.append(card_id)
        return {"card_id": card_id, "title": "Frontier card"}

    screen = CardScreen(_Services(get_frontier_card=get_frontier_card)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    card_input, load = row.controls
    output = screen.controls[3]
    assert isinstance(card_input, ft.TextField)
    assert isinstance(load, ft.Button)
    assert isinstance(output, ft.Text)

    _click(load)
    assert output.value == "Card id is required."
    assert calls == []

    card_input.value = "c1"
    _click(load)
    assert calls == ["c1"]
    assert '"card_id": "c1"' in str(output.value)


def test_card_screen_reports_service_error() -> None:
    def fail(_card_id: str) -> dict[str, object] | None:
        raise RuntimeError("lookup failed")

    screen = CardScreen(_Services(get_frontier_card=fail)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    card_input, load = row.controls
    output = screen.controls[3]
    assert isinstance(card_input, ft.TextField)
    assert isinstance(load, ft.Button)
    assert isinstance(output, ft.Text)
    card_input.value = "c1"

    _click(load)

    assert output.value == "Error: lookup failed"
