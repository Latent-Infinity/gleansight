from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import flet as ft


@dataclass
class SearchScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            "Discover new papers from Semantic Scholar. Use this search to find candidates "
            "to import and index. Imported papers are processed by the job runner.",
            color=ft.Colors.GREY_700,
            size=12,
        )
        status_text = ft.Text("", color=ft.Colors.RED_600, visible=False)
        query_input = ft.TextField(label="Search", expand=True)
        year_min_input = ft.TextField(label="Year from", width=140, hint_text="e.g. 2019")
        year_max_input = ft.TextField(label="Year to", width=140, hint_text="e.g. 2024")
        pub_date_from = ft.TextField(label="Pub date from", width=160, hint_text="YYYY-MM-DD")
        pub_date_to = ft.TextField(label="Pub date to", width=160, hint_text="YYYY-MM-DD")
        fields_input = ft.TextField(label="Fields of study", width=240, hint_text="e.g. Computer Science")
        venue_input = ft.TextField(label="Venue", width=200, hint_text="e.g. NeurIPS")
        pub_types_input = ft.TextField(
            label="Publication types",
            width=220,
            hint_text="e.g. Journal,Conference",
        )
        min_citations_input = ft.TextField(label="Min citations", width=160, hint_text="e.g. 50")
        ui_settings = getattr(self.services, "ui_settings", {}) or {}
        open_access_default = ui_settings.get("require_open_access", False)
        open_access_switch = ft.Switch(label="Open access PDF only", value=open_access_default)
        default_max_results = ui_settings.get("search_max_results", 10)
        api_key_set = bool(ui_settings.get("scholar_api_key_set"))
        rate_limit = ui_settings.get("scholar_rate_limit", 10)
        max_results_input = ft.TextField(
            label="Max results",
            value=str(default_max_results),
            width=140,
        )
        results_view = ft.ListView(expand=True, spacing=10, padding=10)
        selection_bar = ft.Row(spacing=8)
        selected_ids: set[str] = set()
        checkbox_by_id: dict[str, ft.Checkbox] = {}
        current_candidates: list[dict[str, Any]] = []

        # Pagination state
        pagination_state: dict[str, Any] = {
            "last_query": "",
            "last_filters": {},
            "current_offset": 0,
            "page_size": default_max_results,
            "has_more": False,
        }
        load_more_button = ft.ElevatedButton(
            "Load more results",
            visible=False,
            on_click=lambda _: _load_more(),
        )
        results_summary = ft.Text("", size=12, color=ft.Colors.GREY_600)

        def _parse_int(value: str | None) -> int | None:
            if not value:
                return None
            try:
                return int(value)
            except ValueError:
                return None

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

        def _build_candidate_card(candidate: dict[str, Any]) -> ft.Control:
            title = candidate.get("title") or "Untitled"
            year = candidate.get("year") or "n/a"
            venue = candidate.get("venue") or "n/a"
            authors = _format_authors(candidate.get("authors_json"))
            abstract = candidate.get("abstract") or "No abstract available."
            imported_at = candidate.get("imported_at")
            imported_paper_id = candidate.get("imported_paper_id")
            rejected_at = candidate.get("rejected_at")
            is_imported = bool(imported_at or imported_paper_id)
            is_rejected = bool(rejected_at)

            # Get pipeline stage for imported papers
            pipeline_stage = None
            has_markdown = False
            if is_imported and imported_paper_id:
                list_paper = getattr(self.services, "list_paper", None)
                if list_paper:
                    paper = list_paper(imported_paper_id)
                    if paper:
                        pipeline_stage = paper.get("pipeline_stage")
                        has_markdown = pipeline_stage in ("converted", "embedded", "analyzed")

            # Build status text based on pipeline stage
            if is_rejected:
                status = "Rejected"
            elif not is_imported:
                status = "New"
            elif pipeline_stage == "analyzed":
                status = "✓ Analyzed"
            elif pipeline_stage == "embedded":
                status = "✓ Indexed"
            elif pipeline_stage == "converted":
                status = "✓ PDF Ready"
            elif pipeline_stage == "downloaded":
                status = "⏳ Converting"
            else:
                status = "⏳ Downloading"

            # Visual styling based on status
            card_border = None
            status_color = ft.Colors.BLUE_400
            if is_imported:
                if has_markdown:
                    card_border = ft.border.all(2, ft.Colors.GREEN_600)
                    status_color = ft.Colors.GREEN_700
                else:
                    card_border = ft.border.all(2, ft.Colors.AMBER_400)
                    status_color = ft.Colors.AMBER_700
            elif is_rejected:
                card_border = ft.border.all(1, ft.Colors.GREY_400)
                status_color = ft.Colors.GREY_600

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

            def on_details(e: ft.ControlEvent) -> None:
                page = getattr(e, "page", None) or getattr(e.control, "page", None)
                if page is None:
                    return
                dialog = ft.AlertDialog(
                    title=ft.Text(title),
                    content=ft.Column(
                        [
                            ft.Text(f"Authors: {authors}"),
                            ft.Text(f"Venue: {venue}"),
                            ft.Text(f"Year: {year}"),
                            ft.Divider(),
                            ft.Text(abstract),
                        ],
                        tight=True,
                        scroll=ft.ScrollMode.AUTO,
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

            def on_import(e: ft.ControlEvent) -> None:
                import_use_case = getattr(self.services, "import_candidate")
                try:
                    import_use_case.import_candidate(candidate_id=candidate["candidate_id"])
                    # Update card appearance
                    status_chip.bgcolor = ft.Colors.GREEN_600
                    status_chip.content = ft.Text("Imported", size=11, color=ft.Colors.WHITE)
                    # Replace import button with "In library" text
                    action_buttons.clear()
                    action_buttons.append(
                        ft.Text("✓ In library", color=ft.Colors.GREEN_600, size=12)
                    )
                    # Show success message
                    status_text.value = f"Imported: {candidate.get('title', 'Unknown')[:50]}"
                    status_text.color = ft.Colors.GREEN_700
                    status_text.visible = True
                    page = getattr(e, "page", None) or getattr(e.control, "page", None)
                    if page:
                        page.update()
                except Exception as exc:
                    status_text.value = f"Import failed: {exc}"
                    status_text.color = ft.Colors.RED_600
                    status_text.visible = True
                    status_text.update()

            def on_reject(e: ft.ControlEvent) -> None:
                reject_use_case = getattr(self.services, "reject_candidate")
                try:
                    reject_use_case.reject(candidate_id=candidate["candidate_id"])
                    # Update card appearance
                    status_chip.bgcolor = ft.Colors.GREY_600
                    status_chip.content = ft.Text("Rejected", size=11, color=ft.Colors.WHITE)
                    # Remove action buttons
                    action_buttons.clear()
                    # Show success message
                    status_text.value = f"Rejected: {candidate.get('title', 'Unknown')[:50]}"
                    status_text.color = ft.Colors.GREEN_700
                    status_text.visible = True
                    page = getattr(e, "page", None) or getattr(e.control, "page", None)
                    if page:
                        page.update()
                except Exception as exc:
                    status_text.value = f"Reject failed: {exc}"
                    status_text.color = ft.Colors.RED_600
                    status_text.visible = True
                    status_text.update()

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

            checkbox = ft.Checkbox(value=False)
            checkbox_by_id[candidate["candidate_id"]] = checkbox

            def on_select_change(_: ft.ControlEvent) -> None:
                if checkbox.value:
                    selected_ids.add(candidate["candidate_id"])
                else:
                    selected_ids.discard(candidate["candidate_id"])
                _update_selection_bar()

            checkbox.on_change = on_select_change

            # Build status chip with appropriate color
            status_chip = ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                bgcolor=status_color,
                border_radius=12,
                content=ft.Text(status, size=11, color=ft.Colors.WHITE),
            )

            # Action buttons - disable import if already imported
            action_buttons = []
            if not is_imported:
                action_buttons.append(
                    ft.ElevatedButton(
                        "Import",
                        on_click=on_import,
                        tooltip="Import this candidate to your local database.",
                    )
                )
            if not is_rejected and not is_imported:
                action_buttons.append(
                    ft.OutlinedButton(
                        "Reject",
                        on_click=on_reject,
                        tooltip="Remove this candidate from the queue.",
                    )
                )
            if is_imported:
                action_buttons.append(
                    ft.Text("✓ In library", color=ft.Colors.GREEN_600, size=12)
                )

            return ft.Card(
                content=ft.Container(
                    padding=10,
                    border=card_border,
                    border_radius=8,
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    checkbox,
                                    ft.Text(title, size=16, weight=ft.FontWeight.BOLD, expand=True),
                                    ft.Row(action_buttons),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Text(authors, size=12, color=ft.Colors.GREY_700),
                            ft.Row(
                                [
                                    _build_chip(f"Venue: {venue}"),
                                    _build_chip(f"Year: {year}"),
                                    status_chip,
                                ],
                                spacing=8,
                            ),
                            abstract_preview_text,
                            abstract_full_text,
                            ft.Row(
                                [
                                    toggle_button,
                                    ft.TextButton("Details", on_click=on_details),
                                ]
                            ),
                        ],
                        spacing=6,
                    ),
                )
            )

        def _update_selection_bar() -> None:
            count = len(selected_ids)
            selection_bar.controls = [
                ft.Text(f"Selected: {count}"),
                ft.TextButton("Select all", on_click=lambda _: _select_all()),
                ft.TextButton("Clear", on_click=lambda _: _clear_selection()),
                ft.ElevatedButton("Import selected", on_click=lambda _: _import_selected()),
                ft.OutlinedButton("Reject selected", on_click=lambda _: _reject_selected()),
            ]
            selection_bar.update()

        def _select_all() -> None:
            selected_ids.clear()
            for candidate in current_candidates:
                cid = candidate["candidate_id"]
                selected_ids.add(cid)
                checkbox = checkbox_by_id.get(cid)
                if checkbox:
                    checkbox.value = True
            _update_selection_bar()
            results_view.update()

        def _clear_selection() -> None:
            selected_ids.clear()
            for checkbox in checkbox_by_id.values():
                checkbox.value = False
            _update_selection_bar()
            results_view.update()

        def _show_notice(message: str, is_error: bool = False) -> None:
            status_text.value = message
            status_text.color = ft.Colors.RED_600 if is_error else ft.Colors.GREEN_700
            status_text.visible = True
            status_text.update()

        def _import_selected() -> None:
            import_candidate = getattr(self.services, "import_candidate")
            try:
                for cid in list(selected_ids):
                    import_candidate.import_candidate(candidate_id=cid)
                _show_notice(f"Imported {len(selected_ids)} papers.", is_error=False)
                _clear_selection()
            except Exception as exc:
                _show_notice(str(exc), is_error=True)

        def _reject_selected() -> None:
            reject_candidate = getattr(self.services, "reject_candidate")
            try:
                for cid in list(selected_ids):
                    reject_candidate.reject(candidate_id=cid)
                _show_notice(f"Rejected {len(selected_ids)} candidates.", is_error=False)
                _clear_selection()
            except Exception as exc:
                _show_notice(str(exc), is_error=True)

        def _build_filters() -> dict[str, Any]:
            """Build filters dict from input fields."""
            filters: dict[str, Any] = {}
            year_min = _parse_int(year_min_input.value)
            year_max = _parse_int(year_max_input.value)
            if year_min is not None:
                filters["year_min"] = year_min
            if year_max is not None:
                filters["year_max"] = year_max
            if pub_date_from.value or pub_date_to.value:
                filters["publication_date_or_year"] = (
                    f"{pub_date_from.value or ''}:{pub_date_to.value or ''}"
                )
            if fields_input.value:
                filters["fields_of_study"] = fields_input.value
            if venue_input.value:
                filters["venue"] = venue_input.value
            if pub_types_input.value:
                filters["publication_types"] = pub_types_input.value
            if min_citations_input.value:
                filters["min_citation_count"] = min_citations_input.value
            if open_access_switch.value:
                filters["open_access_pdf"] = True
            return filters

        def _fetch_and_display(query: str, filters: dict[str, Any], page_size: int, append: bool = False) -> None:
            """Fetch results and update display."""
            discover = getattr(self.services, "discover")
            get_candidate = getattr(self.services, "get_candidate")

            try:
                candidate_ids = discover.discover(
                    query=query,
                    filters=filters,
                    max_results=page_size,
                )
                candidates = [get_candidate(cid) for cid in candidate_ids]
                new_candidates = [cand for cand in candidates if cand is not None]

                if append:
                    current_candidates.extend(new_candidates)
                    for cand in new_candidates:
                        results_view.controls.append(_build_candidate_card(cand))
                else:
                    current_candidates.clear()
                    current_candidates.extend(new_candidates)
                    selected_ids.clear()
                    checkbox_by_id.clear()
                    results_view.controls = [
                        _build_candidate_card(cand) for cand in current_candidates
                    ]

                # Update pagination state
                pagination_state["has_more"] = len(candidate_ids) >= page_size
                pagination_state["current_offset"] += len(candidate_ids)
                load_more_button.visible = pagination_state["has_more"]

                # Update summary
                total = len(current_candidates)
                total_imported = sum(1 for c in current_candidates if c.get("imported_paper_id"))
                results_summary.value = (
                    f"Showing {total} results ({total_imported} already in library, "
                    f"{total - total_imported} new)"
                )
                results_summary.visible = total > 0

                _update_selection_bar()
                results_view.update()
                load_more_button.update()
                results_summary.update()

            except Exception as exc:
                message = str(exc)
                if "rate limit" in message.lower() or "429" in message:
                    message = "Rate limited by Semantic Scholar. Please wait a bit and try again."
                status_text.value = message
                status_text.visible = True
                status_text.update()

        def _load_more() -> None:
            """Load more results for the current search."""
            if not pagination_state["has_more"]:
                return
            _fetch_and_display(
                query=pagination_state["last_query"],
                filters=pagination_state["last_filters"],
                page_size=pagination_state["page_size"],
                append=True,
            )

        def on_search(_: ft.ControlEvent) -> None:
            query = query_input.value or ""
            page_size = _parse_int(max_results_input.value) or 10
            if page_size < 1:
                page_size = 1
            if page_size > 100:
                page_size = 100
            max_results_input.value = str(page_size)

            filters = _build_filters()

            # Reset pagination state for new search
            pagination_state["last_query"] = query
            pagination_state["last_filters"] = filters
            pagination_state["current_offset"] = 0
            pagination_state["page_size"] = page_size
            pagination_state["has_more"] = False

            status_text.value = ""
            status_text.visible = False
            load_more_button.visible = False
            results_summary.visible = False

            _fetch_and_display(query, filters, page_size, append=False)

        query_input.on_submit = on_search

        return ft.Column(
            [
                instructions,
                status_text,
                ft.Row(
                    [
                        query_input,
                        ft.ElevatedButton(
                            "Search",
                            on_click=on_search,
                            tooltip="Find candidate papers on Semantic Scholar.",
                        ),
                    ]
                ),
                ft.ExpansionPanelList(
                    controls=[
                        ft.ExpansionPanel(
                            header=ft.ListTile(title=ft.Text("Filters")),
                            content=ft.Column(
                                [
                                    ft.Row([year_min_input, year_max_input, max_results_input]),
                                    ft.Row([pub_date_from, pub_date_to, min_citations_input]),
                                    ft.Row([fields_input, venue_input, pub_types_input]),
                                    ft.Row([open_access_switch]),
                                ],
                                spacing=10,
                            ),
                            expanded=False,
                        )
                    ]
                ),
                selection_bar,
                results_summary,
                results_view,
                ft.Row(
                    [load_more_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if api_key_set else ft.Icons.ERROR_OUTLINE,
                            size=14,
                            color=ft.Colors.GREEN_600 if api_key_set else ft.Colors.RED_600,
                            tooltip=(
                                "Semantic Scholar API key detected."
                                if api_key_set
                                else "Semantic Scholar API key not set. Set SEMANTIC_SCHOLAR_API_KEY or config."
                            ),
                        ),
                        ft.Text(
                            f"S2 key {'set' if api_key_set else 'missing'} · RPS {rate_limit}",
                            size=11,
                            color=ft.Colors.GREY_700,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            expand=True,
            spacing=4,
        )
