from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class ArchiveScreen:
    services: object

    def build(self) -> ft.Control:
        output = ft.ListView(expand=True, spacing=8, padding=8)
        status = ft.Text(value="", size=12)
        snapshot = ft.TextField(label="Snapshot id", expand=True)
        policy = ft.TextField(label="Domain policy id", value="finance/1", width=220)
        state = ft.TextField(label="Snapshot state", value="calibration", width=180)
        rank_output = ft.Text(value="", selectable=True)

        def load(_: ft.ControlEvent) -> None:
            lister = getattr(self.services, "list_archive_elites", None)
            output.controls.clear()
            if lister is None:
                status.value = "Archive is not configured."
            else:
                try:
                    elites = lister()
                    status.value = f"{len(elites)} elite card(s)" if elites else "No elite cards."
                    for card in elites:
                        title = str(card.get("title") or card.get("card_id") or "untitled")
                        cell = str(card.get("cell_id") or "")
                        viability = card.get("viability")
                        output.controls.append(
                            ft.Text(value=f"{title}  cell={cell}  viability={viability}")
                        )
                except Exception as exc:
                    status.value = f"Error: {public_ui_error(exc)}"
            status.update()
            output.update()

        def rank(_: ft.ControlEvent) -> None:
            ranker = getattr(self.services, "rank_archive", None)
            snapshot_id = str(snapshot.value or "").strip()
            if not snapshot_id:
                rank_output.value = "Snapshot id is required."
            elif ranker is None:
                rank_output.value = "Archive ranking is not configured."
            else:
                try:
                    result = ranker(
                        snapshot_id=snapshot_id,
                        domain_policy_id=str(policy.value or "").strip(),
                        snapshot_state=str(state.value or "").strip(),
                    )
                    rank_output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    rank_output.value = f"Error: {public_ui_error(exc)}"
            rank_output.update()

        return ft.Column(
            [
                ft.Text(value="Archive", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Elite Frontier Cards currently occupying archive cells.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Button("Refresh", on_click=load),
                status,
                output,
                ft.Row(
                    [snapshot, policy, state, ft.Button("Run rank guard", on_click=rank)], wrap=True
                ),
                rank_output,
            ],
            expand=True,
            spacing=12,
        )
