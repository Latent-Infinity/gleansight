from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from papers.ui.screens.paper import PaperDetailScreen


@dataclass
class FakeServices:
    def list_paper(self, paper_id: str):
        if paper_id == "p1":
            return {"title": "Paper", "year": 2024}
        return None

    def list_runs(self, paper_id: str):
        return [{"run_id": "run-1", "status": "succeeded"}]


def test_paper_detail_builds() -> None:
    services = FakeServices()
    screen = PaperDetailScreen(services)

    control = screen.build()

    assert isinstance(control, ft.Control)
