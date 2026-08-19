from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.screens.monitor import JobsTable, MonitorScreen, RunHistoryTable


@dataclass
class FakeServices:
    def list_jobs(self, _paper_id: str | None = None, _limit: int = 200) -> list[dict[str, Any]]:
        return [
            {
                "job_id": "job-1",
                "type": "download",
                "status": "queued",
                "paper_id": "paper-1",
                "attempts": 1,
                "max_attempts": 3,
            },
            {
                "job_id": "job-2",
                "type": "convert",
                "status": "succeeded",
                "paper_id": "paper-1",
                "attempts": 1,
                "max_attempts": 3,
            },
            {
                "job_id": "job-3",
                "type": "analyze",
                "status": "failed",
                "paper_id": "paper-1",
                "run_id": "run-1",
                "payload_json": '{"model_name":"test-model"}',
                "attempts": 3,
                "max_attempts": 3,
                "created_at": "2026-01-01T01:00:00",
                "updated_at": "2026-01-01T01:02:00",
            },
        ]

    def list_paper(self, paper_id: str) -> dict[str, Any] | None:
        if paper_id == "paper-1":
            return {"title": "Test Paper Title", "paper_id": "paper-1"}
        return None

    def bulk_delete_jobs(self, job_ids: list[str]) -> int:
        return len(job_ids)

    def bulk_cancel_jobs(self, job_ids: list[str]) -> int:
        return len(job_ids)


def _make_table() -> tuple[JobsTable, MagicMock, ft.Row]:
    """Create a JobsTable with a mock page for testing."""
    status_text = ft.Text(value="")
    stats_text = ft.Text(value="")
    selection_count_text = ft.Text(value="0 selected")
    bulk_action_row = ft.Row(
        [selection_count_text, ft.Button("Delete Selected"), ft.Button("Cancel Selected")],
        visible=False,
    )
    table = JobsTable(FakeServices(), status_text, stats_text, bulk_action_row)
    mock_page = MagicMock()
    return table, mock_page, bulk_action_row


def test_monitor_builds() -> None:
    services = FakeServices()
    screen = MonitorScreen(services)

    control = screen.build()

    assert isinstance(control, ft.Control)


def test_refresh_jobs_skipped_while_dialog_active() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table.refresh_jobs()
        assert table._stats_text.value != ""

        # Set active dialog and refresh again
        table._active_dialog = ft.AlertDialog(title=ft.Text(value="test"))
        table._stats_text.value = "stale"
        table.refresh_jobs()

        # Stats should remain stale because refresh was skipped
        assert table._stats_text.value == "stale"


def test_refresh_jobs_resumes_after_dialog_closed() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._active_dialog = ft.AlertDialog(title=ft.Text(value="test"))

        table.refresh_jobs()
        assert table._stats_text.value == ""  # refresh was skipped

        table._active_dialog = None
        table.refresh_jobs()
        assert "Jobs shown:" in table._stats_text.value  # refresh ran


def test_show_dialog_sets_active_dialog() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        dialog = ft.AlertDialog(title=ft.Text(value="test"))

        table._show_dialog(dialog)

        assert table._active_dialog is dialog
        mock_page.show_dialog.assert_called_once_with(dialog)
        assert dialog.on_dismiss is not None


def test_show_dialog_on_dismiss_clears_active_dialog() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        dialog = ft.AlertDialog(title=ft.Text(value="test"))
        table._show_dialog(dialog)

        # Simulate dismiss (e.g. user presses Escape)
        dialog.on_dismiss(MagicMock())

        assert table._active_dialog is None


def test_close_dialog_clears_active_dialog() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        dialog = ft.AlertDialog(title=ft.Text(value="test"))
        table._active_dialog = dialog

        table._close_dialog()

        assert table._active_dialog is None
        mock_page.pop_dialog.assert_called_once()


def test_close_dialog_noop_when_no_dialog() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        assert table._active_dialog is None

        table._close_dialog()  # should not raise

        assert table._active_dialog is None
        mock_page.pop_dialog.assert_called_once()


# --- Selection state tests ---


def test_selection_state_persists_across_refresh() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._selected_job_ids.add("job-1")
        table.refresh_jobs()
        assert "job-1" in table._selected_job_ids


def test_selection_pruned_for_missing_jobs() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._selected_job_ids.add("nonexistent-job")
        table.refresh_jobs()
        assert "nonexistent-job" not in table._selected_job_ids


def test_select_all_selects_visible_jobs() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        mock_event = MagicMock()
        mock_event.control.value = True
        table._on_select_all_changed(mock_event)
        assert "job-1" in table._selected_job_ids
        assert "job-2" in table._selected_job_ids


def test_deselect_all_clears_selection() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._selected_job_ids.add("job-1")
        mock_event = MagicMock()
        mock_event.control.value = False
        table._on_select_all_changed(mock_event)
        assert len(table._selected_job_ids) == 0


def test_clear_selection_empties_set() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._selected_job_ids.add("job-1")
        table._clear_selection()
        assert len(table._selected_job_ids) == 0


def test_bulk_action_bar_visible_when_selected() -> None:
    table, _, bulk_action_row = _make_table()
    table._selected_job_ids.add("job-1")
    table._update_bulk_action_bar()
    assert bulk_action_row.visible is True
    assert bulk_action_row.controls[0].value == "1 selected"


def test_bulk_action_bar_hidden_when_none_selected() -> None:
    table, _, bulk_action_row = _make_table()
    table._update_bulk_action_bar()
    assert bulk_action_row.visible is False


def test_filter_change_clears_selection() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._selected_job_ids.add("job-1")
        table.set_status_filter("succeeded")
        assert len(table._selected_job_ids) == 0


def test_limit_change_clears_selection() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table._selected_job_ids.add("job-1")
        table.set_limit(50)
        assert len(table._selected_job_ids) == 0


def test_select_all_checkbox_state_syncs() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        # Select all visible jobs
        table._selected_job_ids = {"job-1", "job-2", "job-3"}
        table._update_select_all_state()
        assert table._select_all_checkbox.value is True

        # Deselect one
        table._selected_job_ids.discard("job-2")
        table._update_select_all_state()
        assert table._select_all_checkbox.value is False


def test_jobs_table_shows_progress_column() -> None:
    table, mock_page, _ = _make_table()
    with patch.object(type(table), "page", new_callable=lambda: property(lambda self: mock_page)):
        table.update = MagicMock()
        table.refresh_jobs()
        assert len(table.columns) == 7
        assert table.columns[4].label.value == "Progress"


def test_run_history_defaults_to_completed() -> None:
    runs_stats_text = ft.Text(value="")
    table = RunHistoryTable(FakeServices(), runs_stats_text)
    table.update = MagicMock()

    table.refresh_runs()

    assert len(table.rows) == 1
    assert "completed" in runs_stats_text.value.lower()


def test_run_history_status_filter_applies() -> None:
    runs_stats_text = ft.Text(value="")
    table = RunHistoryTable(FakeServices(), runs_stats_text)
    table.update = MagicMock()

    table.set_status_filter("running")

    assert len(table.rows) == 0
