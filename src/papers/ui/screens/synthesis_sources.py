from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from papers.domain.synthesis_grounding import GroundedSource, verify_source


@dataclass(frozen=True, slots=True)
class SourcePassage:
    source: GroundedSource
    get_markdown: Callable[[str], str | None]

    def build(self) -> ft.Control:
        source = self.source
        state = ft.Text("Reference checked when opened", size=12)

        def open_source(event: ft.Event[ft.TextButton]) -> None:
            markdown = self.get_markdown(source.paper_id)
            status = verify_source(source, markdown.encode() if markdown is not None else None)
            state.value = {
                "valid": "Current source verified",
                "stale": "Stale reference: paper changed",
                "missing": "Source Markdown is missing",
            }[status]
            state.color = ft.Colors.GREY_700 if status == "valid" else ft.Colors.RED_700
            content = ft.Column(
                [
                    ft.Text(state.value, color=state.color),
                    ft.Text(
                        f"{source.section} · bytes {source.byte_start}–{source.byte_end}", size=12
                    ),
                    ft.Text("Cited passage", weight=ft.FontWeight.BOLD),
                    ft.Text(source.quote, selectable=True),
                    ft.Divider(),
                    ft.Text("Current paper Markdown", weight=ft.FontWeight.BOLD),
                    ft.Markdown(markdown or "Markdown unavailable", selectable=True),
                ],
                scroll=ft.ScrollMode.AUTO,
                width=800,
                height=600,
            )
            page = event.page
            dialog = ft.AlertDialog(
                title=ft.Text(source.title),
                content=content,
                actions=[ft.TextButton("Close", on_click=lambda _: page.pop_dialog())],
            )
            page.show_dialog(dialog)
            state.update()

        return ft.Column(
            [
                ft.Text(source.title, size=12),
                ft.Text(source.excerpt_id, size=12, selectable=True),
                ft.TextButton(f"Open supporting passage · {source.section}", on_click=open_source),
                ft.Text(source.quote, selectable=True, size=12),
                state,
            ],
            spacing=4,
        )
