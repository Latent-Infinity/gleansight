from __future__ import annotations

import asyncio
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


def _status_color(status: str) -> str:
    """Return color for job status."""
    colors = {
        "queued": ft.Colors.BLUE_400,
        "running": ft.Colors.ORANGE_400,
        "succeeded": ft.Colors.GREEN_400,
        "failed": ft.Colors.RED_400,
        "retryable": ft.Colors.AMBER_400,
    }
    return colors.get(status, ft.Colors.GREY_400)


class JobsTable(ft.DataTable):
    """Auto-refreshing jobs table using background task."""

    def __init__(self, services: object) -> None:
        super().__init__(
            columns=[
                ft.DataColumn(ft.Text("Paper")),
                ft.DataColumn(ft.Text("Job Type")),
                ft.DataColumn(ft.Text("Status")),
            ],
            rows=[],
        )
        self.services = services
        self._running = False

    def did_mount(self) -> None:
        self._running = True
        self.page.run_task(self._auto_refresh)

    def will_unmount(self) -> None:
        self._running = False

    async def _auto_refresh(self) -> None:
        while self._running:
            self.refresh_jobs()
            await asyncio.sleep(2)

    def refresh_jobs(self) -> None:
        list_jobs = getattr(self.services, "list_jobs")
        jobs = list_jobs()
        self.rows = [self._build_row(job) for job in jobs]
        self.update()

    def _build_row(self, job: dict[str, Any]) -> ft.DataRow:
        paper_title = _get_paper_title(self.services, job.get("paper_id"))
        status = job.get("status", "unknown")
        return ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(paper_title)),
                ft.DataCell(ft.Text(job.get("type", "-"))),
                ft.DataCell(
                    ft.Container(
                        content=ft.Text(status, color=ft.Colors.WHITE, size=12),
                        bgcolor=_status_color(status),
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        border_radius=4,
                    )
                ),
            ]
        )


@dataclass
class MonitorScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            "Monitor job queue and analysis runs. Start processing via "
            "`papers run-jobs` in another terminal.",
            color=ft.Colors.GREY_700,
        )
        jobs_table = JobsTable(self.services)

        def on_refresh(_: ft.ControlEvent | None) -> None:
            jobs_table.refresh_jobs()

        return ft.Column(
            [
                instructions,
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Refresh",
                            on_click=on_refresh,
                            tooltip="Reload job status from the database.",
                        )
                    ]
                ),
                jobs_table,
            ],
            expand=True,
        )
