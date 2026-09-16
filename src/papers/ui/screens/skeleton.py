from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class SkeletonScreen:
    services: object

    def build(self) -> ft.Control:
        fixture = ft.TextField(label="Candidate fixture path", expand=True)
        axiom = ft.TextField(label="Axiom", expand=True)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            skeleton = getattr(self.services, "run_skeleton_loop", None)
            fixture_path = str(fixture.value or "").strip()
            axiom_text = str(axiom.value or "").strip()
            if not fixture_path or not axiom_text:
                output.value = "Candidate fixture path and axiom are required."
            elif skeleton is None:
                output.value = "Skeleton is not configured."
            else:
                try:
                    result = skeleton(
                        candidate_fixture=fixture_path,
                        axiom=axiom_text,
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Skeleton", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Run the smoke diverge/ground/score loop on an empty snapshot.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row([fixture, axiom, ft.Button("Run", on_click=run)], wrap=True),
                output,
            ],
            expand=True,
            spacing=12,
        )
