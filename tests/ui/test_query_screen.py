from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from papers.ui.screens.query import QueryScreen


@dataclass
class FakeServices:
    def search(self, *, query: str, limit: int):
        return [{"paper_id": "p1", "score": 0.9}]


def test_query_builds() -> None:
    services = FakeServices()
    screen = QueryScreen(services)

    control = screen.build()

    assert isinstance(control, ft.Control)
