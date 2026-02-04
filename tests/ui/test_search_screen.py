from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from papers.ui.screens.search import SearchScreen


@dataclass
class FakeDiscover:
    def discover(self, *, query: str, filters: dict, max_results: int):
        return ["cand-1"]


@dataclass
class FakeImport:
    def import_candidate(self, *, candidate_id: str):
        return "paper-1"


@dataclass
class FakeReject:
    def reject(self, *, candidate_id: str):
        return None


@dataclass
class FakeCandidateStore:
    def get_candidate(self, candidate_id: str):
        return {
            "candidate_id": candidate_id,
            "title": "Example Paper",
            "year": 2024,
            "venue": "TestConf",
            "authors_json": "[]",
            "abstract": "Abstract",
        }


def test_search_screen_builds() -> None:
    services = type(
        "Services",
        (),
        {
            "discover": FakeDiscover(),
            "import_candidate": FakeImport(),
            "reject_candidate": FakeReject(),
            "get_candidate": FakeCandidateStore().get_candidate,
        },
    )()
    screen = SearchScreen(services)

    control = screen.build()

    assert isinstance(control, ft.Control)


def test_search_screen_uses_require_open_access_from_settings() -> None:
    """Test that open access switch uses require_open_access from ui_settings."""
    services = type(
        "Services",
        (),
        {
            "discover": FakeDiscover(),
            "import_candidate": FakeImport(),
            "reject_candidate": FakeReject(),
            "get_candidate": FakeCandidateStore().get_candidate,
            "ui_settings": {"require_open_access": True},
        },
    )()
    screen = SearchScreen(services)

    control = screen.build()

    # The control is a Column; find the Switch within it
    assert isinstance(control, ft.Column)
    # The switch should be in the filters ExpansionPanelList
    # Find all Switch controls recursively
    def find_switches(ctrl: ft.Control) -> list[ft.Switch]:
        switches = []
        if isinstance(ctrl, ft.Switch):
            switches.append(ctrl)
        if hasattr(ctrl, "controls"):
            for child in ctrl.controls:
                switches.extend(find_switches(child))
        if hasattr(ctrl, "content"):
            if ctrl.content:
                switches.extend(find_switches(ctrl.content))
        return switches

    switches = find_switches(control)
    # Find the open access switch
    open_access_switches = [s for s in switches if "Open access" in (s.label or "")]
    assert len(open_access_switches) == 1
    assert open_access_switches[0].value is True
