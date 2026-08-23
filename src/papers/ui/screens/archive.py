from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass
class ArchiveScreen:
    services: object

    def build(self) -> ft.Control:
        output = ft.ListView(expand=True, spacing=8, padding=8)
        status = ft.Text(value="", size=12)

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
                    status.value = f"Error: {exc}"
            status.update()
            output.update()

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
            ],
            expand=True,
            spacing=12,
        )
