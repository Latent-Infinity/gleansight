from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import flet as ft


@dataclass
class QueryScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            "Search across indexed papers already in your local database.",
            color=ft.Colors.GREY_700,
        )
        query_input = ft.TextField(label="Query", expand=True)
        results_view = ft.ListView(expand=True, spacing=10, padding=10)

        def _format_authors(raw: str | None) -> str:
            if not raw:
                return "Unknown authors"
            try:
                authors = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return "Unknown authors"
            if not authors:
                return "Unknown authors"
            return ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")

        def _build_chip(label: str) -> ft.Control:
            return ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                bgcolor=ft.Colors.GREY_200,
                border_radius=12,
                content=ft.Text(label, size=11),
            )

        def _build_result_card(hit: dict[str, Any]) -> ft.Control:
            paper = hit.get("paper") or {}
            title = paper.get("title") or "Untitled"
            year = paper.get("year") or "n/a"
            venue = paper.get("venue") or "n/a"
            authors = _format_authors(paper.get("authors_json"))
            abstract = paper.get("abstract") or "No abstract available."
            pipeline_stage = paper.get("pipeline_stage", "imported")
            has_markdown = pipeline_stage in ("converted", "embedded", "analyzed")

            # Build status text based on pipeline stage
            if pipeline_stage == "analyzed":
                status_text = "✓ Analyzed"
                status_color = ft.Colors.GREEN_700
            elif pipeline_stage == "embedded":
                status_text = "✓ Indexed"
                status_color = ft.Colors.GREEN_600
            elif pipeline_stage == "converted":
                status_text = "✓ PDF Ready"
                status_color = ft.Colors.GREEN_600
            elif pipeline_stage == "downloaded":
                status_text = "⏳ Converting"
                status_color = ft.Colors.AMBER_700
            else:
                status_text = "⏳ Downloading"
                status_color = ft.Colors.AMBER_700

            abstract_preview = abstract
            if len(abstract) > 280:
                abstract_preview = abstract[:277].rstrip() + "..."
            abstract_preview_text = ft.Text(
                abstract_preview,
                max_lines=3,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
            abstract_full_text = ft.Text(abstract, visible=False)
            toggle_button = ft.TextButton("Show more")

            def on_toggle(e: ft.ControlEvent) -> None:
                abstract_full_text.visible = not abstract_full_text.visible
                abstract_preview_text.visible = not abstract_full_text.visible
                toggle_button.text = "Show less" if abstract_full_text.visible else "Show more"
                page = getattr(e, "page", None) or getattr(e.control, "page", None)
                if page:
                    page.update()

            toggle_button.on_click = on_toggle
            if abstract == "No abstract available.":
                toggle_button.visible = False

            def on_details(e: ft.ControlEvent) -> None:
                page = getattr(e, "page", None) or getattr(e.control, "page", None)
                if page is None:
                    return

                # Try to get the markdown content
                paper_id = hit.get("paper_id") or paper.get("paper_id")
                get_markdown = getattr(self.services, "get_paper_markdown", None)
                markdown_content = None
                if get_markdown and paper_id:
                    markdown_content = get_markdown(paper_id)

                # Build content based on what's available
                if markdown_content:
                    # Show full document with markdown
                    content_controls = [
                        ft.Text(f"Authors: {authors}", size=12, color=ft.Colors.GREY_700),
                        ft.Text(f"Venue: {venue} · Year: {year}", size=12, color=ft.Colors.GREY_700),
                        ft.Divider(),
                        ft.Markdown(
                            markdown_content,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            expand=True,
                        ),
                    ]
                else:
                    # Fallback to abstract only
                    content_controls = [
                        ft.Text(f"Authors: {authors}"),
                        ft.Text(f"Venue: {venue}"),
                        ft.Text(f"Year: {year}"),
                        ft.Divider(),
                        ft.Text(
                            "Full document not available. Paper may still be processing.",
                            italic=True,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Divider(),
                        ft.Text("Abstract:", weight=ft.FontWeight.BOLD),
                        ft.Text(abstract),
                    ]

                dialog = ft.AlertDialog(
                    title=ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                    content=ft.Container(
                        width=800,
                        height=600,
                        content=ft.Column(
                            content_controls,
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                    ),
                    actions=[ft.TextButton("Close", on_click=lambda _: _close_dialog(page))],
                )
                if hasattr(page, "show_dialog"):
                    page.show_dialog(dialog)
                else:
                    page.dialog = dialog
                    dialog.open = True
                    page.update()

            def _close_dialog(page: ft.Page) -> None:
                if hasattr(page, "pop_dialog"):
                    page.pop_dialog()
                elif page.dialog:
                    page.dialog.open = False
                    page.update()

            # Build status chip
            status_chip = ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                bgcolor=status_color,
                border_radius=12,
                content=ft.Text(status_text, size=11, color=ft.Colors.WHITE),
            )

            # Card border based on whether markdown is ready
            card_border = ft.border.all(2, ft.Colors.GREEN_600) if has_markdown else ft.border.all(2, ft.Colors.AMBER_400)

            return ft.Card(
                content=ft.Container(
                    padding=10,
                    border=card_border,
                    border_radius=8,
                    content=ft.Column(
                        [
                            ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
                            ft.Text(authors, size=12, color=ft.Colors.GREY_700),
                            ft.Row(
                                [
                                    _build_chip(f"Venue: {venue}"),
                                    _build_chip(f"Year: {year}"),
                                    _build_chip(f"Score: {hit.get('score', 0):.3f}"),
                                    status_chip,
                                ],
                                spacing=8,
                            ),
                            abstract_preview_text,
                            abstract_full_text,
                            ft.Row([toggle_button, ft.TextButton("Details", on_click=on_details)]),
                        ],
                        spacing=6,
                    ),
                )
            )

        def on_query(_: ft.ControlEvent) -> None:
            query = query_input.value or ""
            search = getattr(self.services, "search")
            list_paper = getattr(self.services, "list_paper")
            hits = search.search(query=query, limit=10)
            enriched = []
            for hit in hits:
                paper = list_paper(hit["paper_id"])
                enriched.append({**hit, "paper": paper})
            results_view.controls = [
                _build_result_card(hit) for hit in enriched if hit.get("paper") is not None
            ]
            results_view.update()

        query_input.on_submit = on_query

        return ft.Column(
            [
                instructions,
                ft.Row(
                    [
                        query_input,
                        ft.ElevatedButton(
                            "Query",
                            on_click=on_query,
                            tooltip="Search across indexed papers already in the local DB.",
                        ),
                    ]
                ),
                results_view,
            ],
            expand=True,
        )
