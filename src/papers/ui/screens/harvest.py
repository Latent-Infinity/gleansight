from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class HarvestScreen:
    services: object

    def build(self) -> ft.Control:
        file_input = ft.TextField(label="Harvest file path", expand=True)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            harvest = getattr(self.services, "harvest_records", None)
            file_path = str(file_input.value or "").strip()
            if not file_path:
                output.value = "Harvest file path is required."
            elif harvest is None:
                output.value = "Harvest is not configured."
            else:
                try:
                    result = harvest(file_path=file_path)
                    record_ids = result.get("record_ids") or []
                    payload = {
                        "accepted": len(record_ids),
                        "record_ids": record_ids,
                        "snapshot_id": result.get("snapshot_id"),
                    }
                    output.value = json.dumps(payload, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Harvest", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Enumerate approved source captures into a versioned corpus snapshot.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row([file_input, ft.Button("Harvest", on_click=run)], wrap=True),
                output,
            ],
            expand=True,
            spacing=12,
        )
