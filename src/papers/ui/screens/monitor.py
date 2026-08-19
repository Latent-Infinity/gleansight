from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft


def _truncate(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _get_paper_title(services: object, paper_id: str | None) -> str:
    """Look up paper title from paper_id, with fallback."""
    if not paper_id:
        return "-"
    list_paper = getattr(services, "list_paper", None)
    if list_paper is None:
        return paper_id[:12] + "..."
    paper = list_paper(paper_id)
    if paper and paper.get("title"):
        return _truncate(paper["title"], 60)
    return paper_id[:12] + "..."


def _status_color(status: str, permanent: bool) -> str:
    """Return color for job status."""
    colors = {
        "queued": ft.Colors.BLUE_400,
        "running": ft.Colors.ORANGE_400,
        "succeeded": ft.Colors.GREEN_400,
        "failed": ft.Colors.RED_400,
        "retryable": ft.Colors.AMBER_400,
        "canceled": ft.Colors.GREY_500,
    }
    if permanent and status == "failed":
        return ft.Colors.GREY_600
    return colors.get(status, ft.Colors.GREY_400)


def _pick_icon(*names: str) -> str:
    for name in names:
        icon = getattr(ft.Icons, name, None)
        if icon is not None:
            return icon
    return getattr(ft.Icons, "HELP_OUTLINE", ft.Icons.ABC)


def _as_time_text(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, str):
        return value.replace("T", " ")[:19]
    to_iso = getattr(value, "isoformat", None)
    if callable(to_iso):
        return str(to_iso()).replace("T", " ")[:19]
    return str(value)


class JobsTable(ft.DataTable):
    """Auto-refreshing jobs table with checkbox selection and bulk actions."""

    def __init__(
        self,
        services: object,
        status_text: ft.Text,
        stats_text: ft.Text,
        bulk_action_row: ft.Row,
        on_after_refresh: Callable[[], None] | None = None,
    ) -> None:
        self._select_all_checkbox = ft.Checkbox(
            value=False,
            on_change=self._on_select_all_changed,
        )
        super().__init__(
            columns=[
                ft.DataColumn(label=self._select_all_checkbox),
                ft.DataColumn(label=ft.Text(value="Paper")),
                ft.DataColumn(label=ft.Text(value="Job Type")),
                ft.DataColumn(label=ft.Text(value="Status")),
                ft.DataColumn(label=ft.Text(value="Progress")),
                ft.DataColumn(label=ft.Text(value="Error")),
                ft.DataColumn(label=ft.Text(value="Action")),
            ],
            rows=[],
        )
        self.services = services
        self._status_text = status_text
        self._stats_text = stats_text
        self._bulk_action_row = bulk_action_row
        self._running = False
        self._status_filter: str | None = None
        self._limit: int = 200
        self._runner_enabled = False
        self._refresh_interval_s = 2
        self._run_next_job = getattr(self.services, "run_next_job", None)
        self._active_dialog: ft.AlertDialog | None = None
        self._selected_job_ids: set[str] = set()
        self._on_after_refresh = on_after_refresh

    def did_mount(self) -> None:
        self._running = True
        self.page.run_task(self._auto_refresh)

    def will_unmount(self) -> None:
        self._running = False

    async def _auto_refresh(self) -> None:
        while self._running:
            if self._runner_enabled and self._run_next_job is not None:
                try:
                    ran = await asyncio.to_thread(self._run_next_job)
                    if ran:
                        self._set_status("Auto-run: processed 1 job")
                    else:
                        self._set_status("Auto-run: idle (no queued jobs)")
                except Exception as exc:  # pragma: no cover - UI safety net
                    self._set_status(f"Auto-run error: {exc}")
            self.refresh_jobs()
            await asyncio.sleep(self._refresh_interval_s)

    def refresh_jobs(self) -> None:
        if self._active_dialog is not None:
            return
        try:
            jobs = self._fetch_jobs()
            jobs = sorted(jobs, key=_sort_key, reverse=True)
            # Prune selections for jobs no longer visible
            visible_ids = {j["job_id"] for j in jobs}
            self._selected_job_ids &= visible_ids
            self.rows = [self._build_row(job) for job in jobs]
            counts = _count_by_status(jobs)
            counts_text = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
            self._stats_text.value = (
                f"Jobs shown: {len(jobs)} | Filter: {self._status_filter or 'all'} | {counts_text}"
            )
            self._set_status("Refreshed")
            self._update_select_all_state(visible_ids)
            self._update_bulk_action_bar()
            try:
                self.update()
            except Exception:
                pass
            if self._on_after_refresh is not None:
                self._on_after_refresh()
        except Exception as exc:  # pragma: no cover - UI safety net
            self._set_status(f"Refresh error: {exc}")
            try:
                self.update()
            except Exception:
                pass

    def _build_row(self, job: dict[str, Any]) -> ft.DataRow:
        job_id = job.get("job_id", "")
        paper_id = job.get("paper_id")
        paper_title = _get_paper_title(self.services, paper_id)
        status = job.get("status", "unknown")
        permanent = _is_permanent_failure(job)
        status_label = "failed (permanent)" if permanent and status == "failed" else status

        def _on_row_checkbox_changed(e: ft.ControlEvent) -> None:
            if e.control.value:
                self._selected_job_ids.add(job_id)
            else:
                self._selected_job_ids.discard(job_id)
            self._update_select_all_state()
            self._update_bulk_action_bar()

        checkbox_cell = ft.DataCell(
            ft.Checkbox(
                value=job_id in self._selected_job_ids,
                on_change=_on_row_checkbox_changed,
            )
        )
        paper_cell = self._build_paper_cell(paper_id, paper_title)
        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or 0)
        progress_text = "-" if max_attempts <= 0 else f"{attempts}/{max_attempts}"
        progress_cell = ft.DataCell(ft.Text(progress_text, size=12))
        error_cell = self._build_error_cell(job)
        action_cell = self._build_action_cell(job, permanent)
        return ft.DataRow(
            cells=[
                checkbox_cell,
                paper_cell,
                ft.DataCell(ft.Text(job.get("type", "-"))),
                ft.DataCell(
                    ft.Container(
                        content=ft.Text(status_label, color=ft.Colors.WHITE, size=12),
                        bgcolor=_status_color(status, permanent),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                        border_radius=4,
                    )
                ),
                progress_cell,
                error_cell,
                action_cell,
            ]
        )

    def _build_paper_cell(self, paper_id: str | None, paper_title: str) -> ft.DataCell:
        if not paper_id:
            return ft.DataCell(ft.Text(paper_title))

        def on_show(_: ft.ControlEvent) -> None:
            list_paper = getattr(self.services, "list_paper", None)
            if list_paper is None:
                return
            paper = list_paper(paper_id) or {}
            title = paper.get("title") or paper_title
            authors = ", ".join(paper.get("authors") or []) or "Unknown authors"
            venue = paper.get("venue") or "Unknown venue"
            year = paper.get("year") or "n/a"
            abstract = paper.get("abstract") or "No abstract available."
            pipeline_stage = paper.get("pipeline_stage") or "-"
            pipeline_health = paper.get("pipeline_health") or "-"
            last_error = paper.get("last_error_message") or "-"

            dialog = ft.AlertDialog(
                title=ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    width=800,
                    height=600,
                    content=ft.Column(
                        [
                            ft.Text(value=f"Authors: {authors}"),
                            ft.Text(value=f"Venue: {venue}"),
                            ft.Text(value=f"Year: {year}"),
                            ft.Text(value=f"Pipeline stage: {pipeline_stage}"),
                            ft.Text(value=f"Pipeline health: {pipeline_health}"),
                            ft.Text(value=f"Last error: {last_error}"),
                            ft.Divider(),
                            ft.Text(value="Abstract:", weight=ft.FontWeight.BOLD),
                            ft.Text(abstract),
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                ),
                actions=[ft.TextButton("Close", on_click=lambda _: self._close_dialog())],
            )
            self._show_dialog(dialog)

        return ft.DataCell(
            ft.TextButton(
                paper_title,
                on_click=on_show,
                tooltip="View paper details.",
            )
        )

    def _build_error_cell(self, job: dict[str, Any]) -> ft.DataCell:
        error = job.get("last_error") or ""
        if not error:
            return ft.DataCell(ft.Text(value="-"))

        def on_show(_: ft.ControlEvent) -> None:
            dialog = ft.AlertDialog(
                title=ft.Text(value="Job error"),
                content=ft.Container(
                    width=720,
                    height=420,
                    content=ft.Column(
                        [
                            ft.Text(value=f"Job ID: {job.get('job_id', '-')}", selectable=True),
                            ft.Text(value=f"Type: {job.get('type', '-')}", selectable=True),
                            ft.Text(value=f"Status: {job.get('status', '-')}", selectable=True),
                            ft.Divider(),
                            ft.Text(error, selectable=True),
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                ),
                actions=[ft.TextButton("Close", on_click=lambda _: self._close_dialog())],
            )
            self._show_dialog(dialog)

        return ft.DataCell(
            ft.TextButton(
                "View",
                on_click=on_show,
                tooltip="View error details.",
            )
        )

    def _build_action_cell(self, job: dict[str, Any], permanent: bool) -> ft.DataCell:
        status = job.get("status")
        if status not in {"failed", "canceled", "succeeded"}:
            return ft.DataCell(ft.Text(value="-"))
        job_type = job.get("type")
        paper_id = job.get("paper_id")
        run_id = job.get("run_id")
        payload = _parse_payload(job.get("payload_json"))
        enqueue_job = getattr(self.services, "enqueue_job", None)
        cancel_job = getattr(self.services, "cancel_job", None)
        delete_job = getattr(self.services, "delete_job", None)
        if enqueue_job is None:
            return ft.DataCell(ft.Text(value="-"))

        def _show_snackbar(message: str) -> None:
            page = self.page
            page.show_dialog(ft.SnackBar(content=ft.Text(message)))

        async def _retry() -> None:
            try:
                await asyncio.to_thread(enqueue_job, job_type, paper_id, run_id, payload)
                self._set_status(f"Requeued {job_type} for {paper_id or '-'}")
            except Exception as exc:
                self._set_status(f"Requeue error: {exc}")
            self.refresh_jobs()

        async def _dismiss() -> None:
            if cancel_job is None:
                return
            try:
                await asyncio.to_thread(cancel_job, job.get("job_id"))
                self._set_status(f"Dismissed {job.get('job_id')}")
            except Exception as exc:
                self._set_status(f"Dismiss error: {exc}")
            self.refresh_jobs()

        def _confirm_delete() -> None:
            if delete_job is None:
                return

            async def _delete() -> None:
                try:
                    await asyncio.to_thread(delete_job, job.get("job_id"))
                    self._set_status(f"Deleted {job.get('job_id')}")
                    _show_snackbar(f"Deleted {job.get('job_id')}")
                except Exception as exc:
                    self._set_status(f"Delete error: {exc}")
                    _show_snackbar(f"Delete error: {exc}")
                self._close_dialog()
                self.refresh_jobs()

            dialog = ft.AlertDialog(
                title=ft.Text(value="Delete job?"),
                content=ft.Text(value="This removes the job record permanently."),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self._close_dialog()),
                    ft.TextButton("Delete", on_click=lambda _: self.page.run_task(_delete)),
                ],
            )
            self._show_dialog(dialog)

        def on_retry(_: ft.ControlEvent) -> None:
            self.page.run_task(_retry)

        def on_dismiss(_: ft.ControlEvent) -> None:
            self.page.run_task(_dismiss)

        def on_delete(_: ft.ControlEvent) -> None:
            _confirm_delete()

        menu_items: list[ft.PopupMenuItem] = []
        if status in {"failed", "canceled"}:
            retry_item = ft.PopupMenuItem(content=ft.Text(value="Retry"), on_click=on_retry)
            if permanent:
                retry_item.disabled = True
            menu_items.append(retry_item)
            menu_items.append(
                ft.PopupMenuItem(content=ft.Text(value="Dismiss"), on_click=on_dismiss)
            )
        if status == "succeeded":
            menu_items.append(ft.PopupMenuItem(content=ft.Text(value="Re-run"), on_click=on_retry))
        menu_items.append(ft.PopupMenuItem(content=ft.Text(value="Delete"), on_click=on_delete))
        return ft.DataCell(
            ft.PopupMenuButton(
                items=menu_items,
                content=ft.Text(value="Actions"),
            )
        )

    # --- Selection management ---

    def _on_select_all_changed(self, e: ft.ControlEvent) -> None:
        checked = bool(e.control.value)
        if checked:
            visible_jobs = self._fetch_jobs()
            self._selected_job_ids = {j["job_id"] for j in visible_jobs}
        else:
            self._selected_job_ids.clear()
        self._update_bulk_action_bar()
        self.refresh_jobs()

    def _update_select_all_state(self, visible_ids: set[str] | None = None) -> None:
        if self._select_all_checkbox is None:
            return
        if visible_ids is None:
            visible_jobs = self._fetch_jobs()
            visible_ids = {j["job_id"] for j in visible_jobs}
        if not visible_ids:
            self._select_all_checkbox.value = False
        elif visible_ids <= self._selected_job_ids:
            self._select_all_checkbox.value = True
        else:
            self._select_all_checkbox.value = False

    def _update_bulk_action_bar(self) -> None:
        count = len(self._selected_job_ids)
        if count > 0:
            self._bulk_action_row.visible = True
            self._bulk_action_row.controls[0].value = f"{count} selected"
        else:
            self._bulk_action_row.visible = False
            self._bulk_action_row.controls[0].value = "0 selected"
        try:
            self._bulk_action_row.update()
        except Exception:
            pass  # May not be mounted yet

    def _clear_selection(self) -> None:
        self._selected_job_ids.clear()
        self._update_select_all_state()
        self._update_bulk_action_bar()
        self.refresh_jobs()

    # --- Bulk actions ---

    def _on_bulk_delete(self, _: ft.ControlEvent) -> None:
        if not self._selected_job_ids:
            return
        count = len(self._selected_job_ids)

        async def _do_delete() -> None:
            bulk_delete = getattr(self.services, "bulk_delete_jobs", None)
            if bulk_delete is None:
                self._set_status("Bulk delete not available")
                return
            try:
                ids = list(self._selected_job_ids)
                deleted = await asyncio.to_thread(bulk_delete, ids)
                self._set_status(f"Deleted {deleted} jobs")
                self._selected_job_ids.clear()
            except Exception as exc:
                self._set_status(f"Bulk delete error: {exc}")
            self._close_dialog()
            self.refresh_jobs()

        dialog = ft.AlertDialog(
            title=ft.Text(value="Delete selected jobs?"),
            content=ft.Text(value=f"This will permanently delete {count} job(s)."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self._close_dialog()),
                ft.TextButton(
                    "Delete",
                    on_click=lambda _: self.page.run_task(_do_delete),
                ),
            ],
        )
        self._show_dialog(dialog)

    def _on_bulk_cancel(self, _: ft.ControlEvent) -> None:
        if not self._selected_job_ids:
            return

        async def _do_cancel() -> None:
            bulk_cancel = getattr(self.services, "bulk_cancel_jobs", None)
            if bulk_cancel is None:
                self._set_status("Bulk cancel not available")
                return
            try:
                ids = list(self._selected_job_ids)
                cancelled = await asyncio.to_thread(bulk_cancel, ids)
                self._set_status(f"Cancelled {cancelled} jobs")
                self._selected_job_ids.clear()
            except Exception as exc:
                self._set_status(f"Bulk cancel error: {exc}")
            self.refresh_jobs()

        self.page.run_task(_do_cancel)

    # --- Filter & runner ---

    def set_status_filter(self, status: str | None) -> None:
        self._status_filter = status
        self._selected_job_ids.clear()
        self.refresh_jobs()

    def set_limit(self, limit: int) -> None:
        self._limit = limit
        self._selected_job_ids.clear()
        self.refresh_jobs()

    def set_filters(self, status: str | None, limit: int) -> None:
        self._status_filter = status
        self._limit = limit
        self._selected_job_ids.clear()
        self.refresh_jobs()

    def set_runner_enabled(self, enabled: bool) -> None:
        self._runner_enabled = enabled

    def _fetch_jobs(self) -> list[dict[str, Any]]:
        list_jobs = self.services.list_jobs
        jobs = list_jobs(None, self._limit)
        if self._status_filter is None:
            return jobs
        if self._status_filter == "retryable":
            return [job for job in jobs if _is_retryable(job)]
        return [job for job in jobs if job.get("status") == self._status_filter]

    def _show_dialog(self, dialog: ft.AlertDialog) -> None:
        def _on_dismiss(_: ft.ControlEvent) -> None:
            self._active_dialog = None

        self._active_dialog = dialog
        dialog.on_dismiss = _on_dismiss
        self.page.show_dialog(dialog)

    def _close_dialog(self) -> None:
        self._active_dialog = None
        self.page.pop_dialog()

    def _set_status(self, message: str) -> None:
        self._status_text.value = message


class RunHistoryTable(ft.DataTable):
    """Read-only run history derived from analyze jobs."""

    def __init__(self, services: object, runs_stats_text: ft.Text) -> None:
        super().__init__(
            columns=[
                ft.DataColumn(label=ft.Text(value="Run ID")),
                ft.DataColumn(label=ft.Text(value="Paper")),
                ft.DataColumn(label=ft.Text(value="Status")),
                ft.DataColumn(label=ft.Text(value="Model")),
                ft.DataColumn(label=ft.Text(value="Started")),
                ft.DataColumn(label=ft.Text(value="Finished")),
            ],
            rows=[],
        )
        self.services = services
        self._runs_stats_text = runs_stats_text
        self._status_filter: str = "completed"
        self._limit: int = 200

    def refresh_runs(self) -> None:
        list_jobs = getattr(self.services, "list_jobs", None)
        if list_jobs is None:
            self.rows = []
            self._runs_stats_text.value = "Run history unavailable"
            return

        jobs = list_jobs(None, self._limit)
        run_jobs = [job for job in jobs if job.get("type") == "analyze" and job.get("run_id")]

        if self._status_filter == "completed":
            run_jobs = [
                job for job in run_jobs if job.get("status") in {"succeeded", "failed", "canceled"}
            ]
        elif self._status_filter not in {"all", ""}:
            run_jobs = [job for job in run_jobs if job.get("status") == self._status_filter]

        run_jobs = sorted(run_jobs, key=_sort_key, reverse=True)
        self.rows = [self._build_row(job) for job in run_jobs]
        counts = _count_by_status(run_jobs)
        counts_text = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "-"
        self._runs_stats_text.value = (
            f"Runs shown: {len(run_jobs)} | Filter: {self._status_filter} | {counts_text}"
        )
        try:
            self.update()
        except Exception:
            pass

    def set_status_filter(self, status: str) -> None:
        self._status_filter = status or "completed"
        self.refresh_runs()

    def set_limit(self, limit: int) -> None:
        self._limit = limit
        self.refresh_runs()

    def set_filters(self, status: str, limit: int) -> None:
        self._status_filter = status or "completed"
        self._limit = limit
        self.refresh_runs()

    def _build_row(self, job: dict[str, Any]) -> ft.DataRow:
        paper_id = job.get("paper_id")
        payload = _parse_payload(job.get("payload_json"))
        model_name = str(payload.get("model_name") or payload.get("model") or "-")
        status = str(job.get("status") or "unknown")
        created = _as_time_text(job.get("created_at"))
        finished = _as_time_text(job.get("updated_at"))
        return ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(str(job.get("run_id", "-")), size=12)),
                ft.DataCell(ft.Text(_get_paper_title(self.services, paper_id), size=12)),
                ft.DataCell(
                    ft.Container(
                        content=ft.Text(status, color=ft.Colors.WHITE, size=12),
                        bgcolor=_status_color(status, permanent=False),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                        border_radius=4,
                    )
                ),
                ft.DataCell(ft.Text(model_name, size=12)),
                ft.DataCell(ft.Text(created, size=11)),
                ft.DataCell(ft.Text(finished, size=11)),
            ]
        )


def _sort_key(job: dict[str, Any]) -> str:
    created_at = job.get("created_at")
    if created_at is None:
        return ""
    if isinstance(created_at, str):
        return created_at
    try:
        return created_at.isoformat()
    except AttributeError:
        return str(created_at)


def _is_retryable(job: dict[str, Any]) -> bool:
    if job.get("status") != "queued":
        return False
    return job.get("run_after") is not None or bool(job.get("last_error"))


def _parse_payload(payload_json: Any) -> dict[str, Any]:
    if not payload_json:
        return {}
    if isinstance(payload_json, dict):
        return payload_json
    try:
        return json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return {}


def _count_by_status(jobs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        status = job.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _is_permanent_failure(job: dict[str, Any]) -> bool:
    if job.get("status") != "failed":
        return False
    error = str(job.get("last_error") or "").lower()
    tokens = (
        "no external ids available to resolve pdf url",
        "could not resolve pdf url",
        "no open pdf",
        "pdf resolver not configured",
        "cannot download without source_path",
    )
    return any(token in error for token in tokens)


@dataclass
class MonitorScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            value="Monitor job queue and analysis runs. Optionally enable the runner below "
            "to process jobs in this UI.",
            color=ft.Colors.GREY_700,
        )
        status_text = ft.Text(value="", size=12, color=ft.Colors.GREY_700)
        stats_text = ft.Text(value="", size=12, color=ft.Colors.GREY_700)
        runs_stats_text = ft.Text(value="", size=12, color=ft.Colors.GREY_700)

        run_history_table = RunHistoryTable(self.services, runs_stats_text)

        # Bulk action bar (hidden until items selected)
        selection_count_text = ft.Text(value="0 selected", size=12, weight=ft.FontWeight.BOLD)
        bulk_action_row = ft.Row(
            [
                selection_count_text,
                ft.Button(
                    "Delete Selected",
                    icon=_pick_icon("DELETE_OUTLINE", "DELETE"),
                    on_click=lambda e: jobs_table._on_bulk_delete(e),
                ),
                ft.Button(
                    "Cancel Selected",
                    icon=_pick_icon("CANCEL_OUTLINED", "CANCEL"),
                    on_click=lambda e: jobs_table._on_bulk_cancel(e),
                ),
                ft.TextButton(
                    "Clear Selection",
                    on_click=lambda _: jobs_table._clear_selection(),
                ),
            ],
            visible=False,
        )

        jobs_table = JobsTable(
            self.services,
            status_text,
            stats_text,
            bulk_action_row,
            on_after_refresh=run_history_table.refresh_runs,
        )

        status_filter = ft.Dropdown(
            label="Status",
            value="all",
            width=200,
            options=[
                ft.dropdown.Option("all", "All"),
                ft.dropdown.Option("queued", "Queued"),
                ft.dropdown.Option("running", "Running"),
                ft.dropdown.Option("succeeded", "Succeeded"),
                ft.dropdown.Option("failed", "Failed"),
                ft.dropdown.Option("retryable", "Retryable (queued w/ backoff)"),
                ft.dropdown.Option("canceled", "Canceled"),
            ],
        )
        limit_filter = ft.Dropdown(
            label="Max rows",
            value="200",
            width=140,
            options=[
                ft.dropdown.Option("50", "50"),
                ft.dropdown.Option("100", "100"),
                ft.dropdown.Option("200", "200"),
                ft.dropdown.Option("500", "500"),
            ],
        )
        run_status_filter = ft.Dropdown(
            label="Run status",
            value="completed",
            width=220,
            options=[
                ft.dropdown.Option("completed", "Completed"),
                ft.dropdown.Option("all", "All"),
                ft.dropdown.Option("queued", "Queued"),
                ft.dropdown.Option("running", "Running"),
                ft.dropdown.Option("succeeded", "Succeeded"),
                ft.dropdown.Option("failed", "Failed"),
                ft.dropdown.Option("canceled", "Canceled"),
            ],
        )
        runner_toggle = ft.Switch(label="Auto-run jobs", value=False)

        def on_filter_change(e: ft.ControlEvent | None) -> None:
            status_value = e.control.value if e else status_filter.value
            status = None if status_value in (None, "all") else status_value
            jobs_table.set_status_filter(status)

        def on_limit_change(e: ft.ControlEvent | None) -> None:
            try:
                limit_value = e.control.value if e else limit_filter.value
                limit = int(limit_value or "200")
            except ValueError:
                limit = 200
            jobs_table.set_limit(limit)
            run_history_table.set_limit(limit)

        def on_run_filter_change(e: ft.ControlEvent | None) -> None:
            status = str(e.control.value if e else run_status_filter.value or "completed")
            run_history_table.set_status_filter(status)

        def on_runner_toggle(e: ft.ControlEvent | None) -> None:
            enabled = bool(getattr(e.control, "value", False)) if e else False
            jobs_table.set_runner_enabled(enabled)

        def on_refresh(_: ft.ControlEvent | None) -> None:
            status_value = status_filter.value
            status = None if status_value in (None, "all") else status_value
            try:
                limit = int(limit_filter.value or "200")
            except ValueError:
                limit = 200
            jobs_table.set_filters(status, limit)
            run_status = str(run_status_filter.value or "completed")
            run_history_table.set_filters(run_status, limit)

        async def _run_once() -> None:
            run_next_job = getattr(self.services, "run_next_job", None)
            if run_next_job is None:
                jobs_table._set_status("Run once unavailable")
                return
            try:
                ran = await asyncio.to_thread(run_next_job)
                jobs_table._set_status("Run once: processed 1 job" if ran else "Run once: idle")
            except Exception as exc:  # pragma: no cover - UI safety net
                jobs_table._set_status(f"Run once error: {exc}")
            jobs_table.refresh_jobs()

        def on_run_once(_: ft.ControlEvent | None) -> None:
            jobs_table.page.run_task(_run_once)

        status_filter.on_select = on_filter_change
        limit_filter.on_select = on_limit_change
        run_status_filter.on_select = on_run_filter_change
        runner_toggle.on_change = on_runner_toggle

        return ft.Column(
            [
                instructions,
                ft.Row(
                    [
                        status_filter,
                        run_status_filter,
                        limit_filter,
                        runner_toggle,
                        ft.OutlinedButton(
                            "Run once",
                            on_click=on_run_once,
                            tooltip="Process a single job now.",
                        ),
                        ft.Button(
                            "Refresh",
                            on_click=on_refresh,
                            tooltip="Reload job status from the database.",
                        ),
                    ]
                ),
                ft.Text(value="Job Queue", size=14, weight=ft.FontWeight.BOLD),
                bulk_action_row,
                ft.Row([stats_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([status_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Column(
                    [jobs_table],
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                ft.Divider(),
                ft.Text(value="Run History", size=14, weight=ft.FontWeight.BOLD),
                ft.Row([runs_stats_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Column(
                    [run_history_table],
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ],
            expand=True,
        )
