from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import flet as ft

from papers.ui.screens.monitor import MonitorScreen


@dataclass
class FakeServices:
    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {"job_id": "job-1", "type": "download", "status": "queued", "paper_id": "paper-1"}
        ]

    def list_paper(self, paper_id: str) -> dict[str, Any] | None:
        if paper_id == "paper-1":
            return {"title": "Test Paper Title", "paper_id": "paper-1"}
        return None


def test_monitor_builds() -> None:
    services = FakeServices()
    screen = MonitorScreen(services)

    control = screen.build()

    assert isinstance(control, ft.Control)
