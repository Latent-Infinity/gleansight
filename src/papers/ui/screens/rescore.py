from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class RescoreScreen:
    services: object

    def build(self) -> ft.Control:
        card_id = ft.TextField(label="Card id", expand=True)
        snapshot = ft.TextField(label="Current snapshot id", expand=True)
        version = ft.TextField(label="Current corpus version", width=180)
        state = ft.TextField(label="Snapshot state", value="calibration", width=160)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            rescore = getattr(self.services, "rescore_card", None)
            card = str(card_id.value or "").strip()
            snapshot_id = str(snapshot.value or "").strip()
            version_text = str(version.value or "").strip()
            if not card or not snapshot_id or not version_text:
                output.value = "Card id, current snapshot id, and corpus version are required."
            elif rescore is None:
                output.value = "Rescore is not configured."
            else:
                try:
                    result = rescore(
                        card_id=card,
                        current_snapshot_id=snapshot_id,
                        current_corpus_version=int(version_text),
                        snapshot_state=str(state.value or "").strip(),
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Rescore", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Re-ground and re-score a persisted card against the current snapshot.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row(
                    [card_id, snapshot, version, state, ft.Button("Rescore", on_click=run)],
                    wrap=True,
                ),
                output,
            ],
            expand=True,
            spacing=12,
        )
