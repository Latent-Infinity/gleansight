from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft


@dataclass
class CardScreen:
    services: object

    def build(self) -> ft.Control:
        card_input = ft.TextField(label="Card id", expand=True)
        output = ft.Text(value="", selectable=True)

        def load(_: ft.ControlEvent) -> None:
            getter = getattr(self.services, "get_frontier_card", None)
            card_id = str(card_input.value or "").strip()
            if not card_id:
                output.value = "Card id is required."
            elif getter is None:
                output.value = "Card lookup is not configured."
            else:
                try:
                    card = getter(card_id)
                    output.value = (
                        "Card not found."
                        if card is None
                        else json.dumps(card, indent=2, default=str)
                    )
                except Exception as exc:
                    output.value = f"Error: {exc}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Card", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Inspect a Frontier Card by id.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row([card_input, ft.Button("Load", on_click=load)]),
                output,
            ],
            expand=True,
            spacing=12,
        )
