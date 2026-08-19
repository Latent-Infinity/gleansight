from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft


def _next_job_type(stage: str | None) -> str | None:
    """Determine the next job type based on the current pipeline stage."""
    if stage in (None, "imported"):
        return "download"
    if stage == "downloaded":
        return "convert"
    if stage == "converted":
        return "embed"
    return None


@dataclass
class QueryScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            value="Search across indexed papers already in your local database.",
            color=ft.Colors.GREY_700,
        )
        query_input = ft.TextField(label="Query", expand=True)
        results_view = ft.ListView(expand=True, spacing=10, padding=10)
        status_bar = ft.Text(value="", size=12)
        aggregation_output = ft.Text(value="", size=12, selectable=True)
        last_results: list[dict[str, Any]] = []

        filter_field_input = ft.TextField(label="Filter field path", width=220)
        filter_prompt_input = ft.TextField(label="Prompt version", width=180)
        filter_kind = ft.Dropdown(
            label="Constraint type",
            value="value_text",
            width=170,
            options=[
                ft.dropdown.Option("value_text", "Text"),
                ft.dropdown.Option("value_numeric", "Numeric"),
                ft.dropdown.Option("value_boolean", "Boolean"),
            ],
        )
        filter_value_input = ft.TextField(label="Constraint value", width=200)
        filter_latest_only = ft.Switch(label="Latest only", value=True)

        aggregate_field_input = ft.TextField(label="Aggregate field path", width=220)
        aggregate_prompt_input = ft.TextField(label="Prompt version", width=180)
        aggregate_op = ft.Dropdown(
            label="Operation",
            value="count",
            width=140,
            options=[
                ft.dropdown.Option("count", "Count"),
                ft.dropdown.Option("average", "Average"),
            ],
        )
        aggregate_group_by_input = ft.TextField(
            label="Group by (optional)",
            width=220,
            hint_text="e.g. value_text",
        )
        aggregate_latest_only = ft.Switch(label="Latest only", value=True)
        export_path_input = ft.TextField(
            label="Export path",
            value="query-results.csv",
            width=320,
        )

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
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=ft.Colors.GREY_200,
                border_radius=12,
                content=ft.Text(label, size=11),
            )

        def _safe_update(control: ft.Control) -> None:
            try:
                control.update()
            except Exception:
                pass

        def _set_status(message: str, is_error: bool = False) -> None:
            status_bar.value = message
            status_bar.color = ft.Colors.RED_700 if is_error else ft.Colors.GREY_700
            _safe_update(status_bar)

        def _parse_constraint_value(kind: str, raw_value: str) -> Any:
            if kind == "value_numeric":
                return float(raw_value)
            if kind == "value_boolean":
                lowered = raw_value.strip().lower()
                if lowered in {"1", "true", "yes"}:
                    return 1
                if lowered in {"0", "false", "no"}:
                    return 0
                raise ValueError("Boolean constraints must be true/false/1/0.")
            return raw_value

        def _build_result_card(hit: dict[str, Any]) -> ft.Control:
            paper = hit.get("paper") or {}
            title = paper.get("title") or "Untitled"
            paper_id = hit.get("paper_id") or paper.get("paper_id")
            year = paper.get("year") or "n/a"
            venue = paper.get("venue") or "n/a"
            authors = _format_authors(paper.get("authors_json"))
            abstract = paper.get("abstract") or "No abstract available."
            pipeline_stage = paper.get("pipeline_stage", "imported")
            pipeline_health = paper.get("pipeline_health", "ok")
            has_markdown = pipeline_stage in ("converted", "embedded", "analyzed")

            # Build status text based on pipeline health and stage
            if pipeline_health == "error":
                status_text = "⚠ Error"
                status_color = ft.Colors.RED_700
            elif pipeline_stage == "analyzed":
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

                get_markdown = getattr(self.services, "get_paper_markdown", None)
                markdown_content = None
                if get_markdown and paper_id:
                    markdown_content = get_markdown(paper_id)

                if markdown_content:
                    content_controls = [
                        ft.Text(value=f"Authors: {authors}", size=12, color=ft.Colors.GREY_700),
                        ft.Text(
                            value=f"Venue: {venue} · Year: {year}",
                            size=12,
                            color=ft.Colors.GREY_700,
                        ),
                        ft.Divider(),
                        ft.Markdown(
                            markdown_content,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            expand=True,
                        ),
                    ]
                else:
                    content_controls = [
                        ft.Text(value=f"Authors: {authors}"),
                        ft.Text(value=f"Venue: {venue}"),
                        ft.Text(value=f"Year: {year}"),
                        ft.Divider(),
                        ft.Text(
                            value="Full document not available. Paper may still be processing.",
                            italic=True,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Divider(),
                        ft.Text(value="Abstract:", weight=ft.FontWeight.BOLD),
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

            # --- Action menu ---
            enqueue_job = getattr(self.services, "enqueue_job", None)
            delete_paper_fn = getattr(self.services, "delete_paper", None)
            reset_stage_fn = getattr(self.services, "reset_pipeline_stage", None)

            def _set_status_message(msg: str) -> None:
                _set_status(msg, is_error=False)

            def _on_retry(_: ft.ControlEvent) -> None:
                if enqueue_job is None or not paper_id:
                    return
                job_type = _next_job_type(pipeline_stage)
                if job_type is None:
                    return
                enqueue_job(job_type, paper_id, None, {})
                _set_status_message(f"Enqueued {job_type} for {title[:50]}")

            def _on_redownload(_: ft.ControlEvent) -> None:
                if enqueue_job is None or not paper_id:
                    return
                enqueue_job("download", paper_id, None, {})
                _set_status_message(f"Enqueued re-download for {title[:50]}")

            def _on_reset(_: ft.ControlEvent) -> None:
                if reset_stage_fn is None or not paper_id:
                    return
                reset_stage_fn(paper_id, "imported")
                _set_status_message(f"Reset {title[:50]} to imported")

            def _on_delete(_: ft.ControlEvent) -> None:
                if delete_paper_fn is None or not paper_id:
                    return
                page = getattr(_, "page", None) or getattr(_.control, "page", None)
                if page is None:
                    return

                async def _do_delete() -> None:
                    await asyncio.to_thread(delete_paper_fn, paper_id)
                    _set_status_message(f"Deleted {title[:50]}")
                    _close_dialog(page)
                    on_query(None)

                dialog = ft.AlertDialog(
                    title=ft.Text(value="Delete paper?"),
                    content=ft.Text(
                        value=f"This removes '{title[:80]}' and all related "
                        "jobs, tags, and analysis runs."
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: _close_dialog(page)),
                        ft.TextButton(
                            "Delete",
                            on_click=lambda _: page.run_task(_do_delete),
                        ),
                    ],
                )
                if hasattr(page, "show_dialog"):
                    page.show_dialog(dialog)
                else:
                    page.dialog = dialog
                    dialog.open = True
                    page.update()

            menu_items: list[ft.PopupMenuItem] = []
            if _next_job_type(pipeline_stage) is not None and enqueue_job is not None:
                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Retry step"), on_click=_on_retry)
                )
            if pipeline_stage not in (None, "imported") and enqueue_job is not None:
                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Re-download"), on_click=_on_redownload)
                )
            if pipeline_stage not in (None, "imported") and reset_stage_fn is not None:
                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Reset to imported"), on_click=_on_reset)
                )
            if delete_paper_fn is not None:
                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Delete"), on_click=_on_delete)
                )

            actions_menu = (
                ft.PopupMenuButton(items=menu_items, content=ft.Text(value="Actions"))
                if menu_items
                else ft.Container()
            )

            # Build status chip
            status_chip = ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=status_color,
                border_radius=12,
                content=ft.Text(status_text, size=11, color=ft.Colors.WHITE),
            )

            # Card border: red for error, green for ready, amber for in-progress
            if pipeline_health == "error":
                card_border = ft.Border.all(2, ft.Colors.RED_400)
            elif has_markdown:
                card_border = ft.Border.all(2, ft.Colors.GREEN_600)
            else:
                card_border = ft.Border.all(2, ft.Colors.AMBER_400)

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
                            ft.Row(
                                [
                                    toggle_button,
                                    ft.TextButton("Details", on_click=on_details),
                                    actions_menu,
                                ]
                            ),
                        ],
                        spacing=6,
                    ),
                )
            )

        def _enrich_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
            list_paper = self.services.list_paper
            enriched: list[dict[str, Any]] = []
            for hit in hits:
                paper = list_paper(hit["paper_id"])
                if paper is None:
                    continue
                enriched.append({**hit, "paper": paper})
            return enriched

        def _render_results(enriched: list[dict[str, Any]]) -> None:
            nonlocal last_results
            last_results = enriched
            results_view.controls = [_build_result_card(hit) for hit in enriched]
            _safe_update(results_view)

        def on_query(_: ft.ControlEvent | None) -> None:
            query = (query_input.value or "").strip()
            if not query:
                _set_status("Enter a query string.", is_error=True)
                _render_results([])
                return
            search = self.services.search
            hits = search.search(query=query, limit=50)
            _render_results(_enrich_hits(hits))
            _set_status(f"Query returned {len(last_results)} papers.")

        def on_apply_filter(_: ft.ControlEvent | None) -> None:
            filter_uc = getattr(self.services, "filter_extractions", None)
            if filter_uc is None:
                _set_status("Extraction filter use-case unavailable.", is_error=True)
                return

            field_path = (filter_field_input.value or "").strip()
            prompt_version_id = (filter_prompt_input.value or "").strip()
            raw_value = (filter_value_input.value or "").strip()
            kind = str(filter_kind.value or "value_text")
            if not field_path or not prompt_version_id:
                _set_status("Filter requires field path and prompt version.", is_error=True)
                return
            if not raw_value:
                _set_status("Filter requires a constraint value.", is_error=True)
                return

            try:
                parsed_value = _parse_constraint_value(kind, raw_value)
            except ValueError as exc:
                _set_status(str(exc), is_error=True)
                return

            constraints = {kind: parsed_value}
            paper_ids = filter_uc.filter(
                field_path=field_path,
                prompt_version_id=prompt_version_id,
                constraints=constraints,
                latest_only=bool(filter_latest_only.value),
            )
            matched_ids = set(paper_ids)
            query_text = (query_input.value or "").strip()

            if query_text:
                search = self.services.search
                hits = search.search(query=query_text, limit=100)
                hits = [hit for hit in hits if hit.get("paper_id") in matched_ids]
            else:
                hits = [{"paper_id": pid, "score": 0.0} for pid in paper_ids]

            _render_results(_enrich_hits(hits))
            _set_status(f"Filter matched {len(last_results)} papers.")

        def on_aggregate(_: ft.ControlEvent | None) -> None:
            aggregate_uc = getattr(self.services, "aggregate_extractions", None)
            if aggregate_uc is None:
                _set_status("Aggregate use-case unavailable.", is_error=True)
                return
            field_path = (aggregate_field_input.value or "").strip()
            prompt_version_id = (aggregate_prompt_input.value or "").strip()
            if not field_path or not prompt_version_id:
                _set_status("Aggregate requires field path and prompt version.", is_error=True)
                return

            operation = str(aggregate_op.value or "count").strip().lower()
            try:
                if operation == "count":
                    result: Any = aggregate_uc.count_by_value(
                        field_path=field_path,
                        prompt_version_id=prompt_version_id,
                        latest_only=bool(aggregate_latest_only.value),
                    )
                elif operation == "average":
                    group_by = (aggregate_group_by_input.value or "").strip() or None
                    result = aggregate_uc.average_numeric(
                        field_path=field_path,
                        prompt_version_id=prompt_version_id,
                        group_by=group_by,
                        latest_only=bool(aggregate_latest_only.value),
                    )
                else:
                    _set_status("Unsupported aggregate operation.", is_error=True)
                    return
            except Exception as exc:
                _set_status(f"Aggregate failed: {exc}", is_error=True)
                return

            aggregation_output.value = json.dumps(result, indent=2, sort_keys=True, default=str)
            _safe_update(aggregation_output)
            _set_status("Aggregation complete.")

        def on_export(_: ft.ControlEvent | None) -> None:
            if not last_results:
                _set_status("No results to export.", is_error=True)
                return
            raw_path = (export_path_input.value or "query-results.csv").strip()
            export_path = Path(raw_path).expanduser()
            try:
                export_path.parent.mkdir(parents=True, exist_ok=True)
                with export_path.open("w", encoding="utf-8", newline="") as csv_file:
                    writer = csv.DictWriter(
                        csv_file,
                        fieldnames=[
                            "paper_id",
                            "score",
                            "title",
                            "year",
                            "venue",
                            "pipeline_stage",
                            "pipeline_health",
                        ],
                    )
                    writer.writeheader()
                    for hit in last_results:
                        paper = hit.get("paper") or {}
                        writer.writerow(
                            {
                                "paper_id": hit.get("paper_id", ""),
                                "score": f"{float(hit.get('score', 0.0)):.6f}",
                                "title": paper.get("title", ""),
                                "year": paper.get("year", ""),
                                "venue": paper.get("venue", ""),
                                "pipeline_stage": paper.get("pipeline_stage", ""),
                                "pipeline_health": paper.get("pipeline_health", ""),
                            }
                        )
            except OSError as exc:
                _set_status(f"Export failed: {exc}", is_error=True)
                return
            _set_status(f"Exported {len(last_results)} rows to {export_path}.")

        query_input.on_submit = on_query

        return ft.Column(
            [
                instructions,
                ft.Row(
                    [
                        query_input,
                        ft.Button(
                            "Query",
                            on_click=on_query,
                            tooltip="Search across indexed papers already in the local DB.",
                        ),
                    ]
                ),
                ft.ExpansionPanelList(
                    controls=[
                        ft.ExpansionPanel(
                            header=ft.ListTile(title=ft.Text(value="Extraction Filter")),
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            filter_field_input,
                                            filter_prompt_input,
                                            filter_kind,
                                            filter_value_input,
                                            filter_latest_only,
                                        ],
                                        wrap=True,
                                    ),
                                    ft.Row(
                                        [
                                            ft.OutlinedButton(
                                                "Apply filter",
                                                on_click=on_apply_filter,
                                                tooltip="Filter papers by extracted values.",
                                            ),
                                        ]
                                    ),
                                ],
                                spacing=10,
                            ),
                        ),
                        ft.ExpansionPanel(
                            header=ft.ListTile(title=ft.Text(value="Aggregations")),
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            aggregate_field_input,
                                            aggregate_prompt_input,
                                            aggregate_op,
                                            aggregate_group_by_input,
                                            aggregate_latest_only,
                                        ],
                                        wrap=True,
                                    ),
                                    ft.Row(
                                        [
                                            ft.OutlinedButton(
                                                "Run aggregation",
                                                on_click=on_aggregate,
                                                tooltip="Run count or average aggregation.",
                                            ),
                                        ]
                                    ),
                                    aggregation_output,
                                ],
                                spacing=10,
                            ),
                        ),
                    ]
                ),
                ft.Row(
                    [
                        export_path_input,
                        ft.Button(
                            "Export CSV",
                            on_click=on_export,
                            tooltip="Export current query results to CSV.",
                        ),
                    ]
                ),
                status_bar,
                results_view,
            ],
            expand=True,
        )
