from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

import flet as ft


@dataclass
class MapScreen:
    services: object

    def build(self) -> ft.Control:
        snapshot_input = ft.TextField(label="Snapshot id", expand=True)
        policy_input = ft.TextField(label="Domain policy id", value="finance/1", width=220)
        state_input = ft.TextField(label="Snapshot state", value="calibration", width=180)
        output = ft.Text(value="", selectable=True)

        def load(_: ft.ControlEvent) -> None:
            mapper = getattr(self.services, "map_snapshot", None)
            snapshot_id = str(snapshot_input.value or "").strip()
            if not snapshot_id:
                output.value = "Snapshot id is required."
            elif mapper is None:
                output.value = "Map is not configured."
            else:
                try:
                    result = mapper(
                        snapshot_id=snapshot_id,
                        domain_policy_id=str(policy_input.value or "").strip(),
                        snapshot_state=str(state_input.value or "").strip(),
                    )
                    statuses = result.get("cell_statuses") or {}
                    counts = Counter(str(status) for status in statuses.values())
                    payload: dict[str, Any] = {
                        "snapshot_id": result.get("snapshot_id"),
                        "domain_policy_id": result.get("domain_policy_id"),
                        "counts": dict(counts),
                    }
                    output.value = json.dumps(payload, indent=2)
                except Exception as exc:
                    output.value = f"Error: {exc}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Map", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Inspect pack-scoped cell statuses for a corpus snapshot.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row(
                    [
                        snapshot_input,
                        policy_input,
                        state_input,
                        ft.Button("Load", on_click=load),
                    ]
                ),
                output,
            ],
            expand=True,
            spacing=12,
        )
