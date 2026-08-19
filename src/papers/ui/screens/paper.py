from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
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


def _build_chip(
    label: str,
    bgcolor: str = ft.Colors.GREY_200,
    text_color: str | None = None,
) -> ft.Control:
    kw: dict[str, Any] = {"size": 11}
    if text_color:
        kw["color"] = text_color
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        bgcolor=bgcolor,
        border_radius=12,
        content=ft.Text(label, **kw),
    )


def _status_info(stage: str | None, health: str | None) -> tuple[str, str, str]:
    """Return (label, bgcolor, text_color) for a pipeline status chip."""
    if health == "error":
        return "error", ft.Colors.RED_700, ft.Colors.WHITE
    if stage == "analyzed":
        return "analyzed", ft.Colors.GREEN_700, ft.Colors.WHITE
    if stage == "embedded":
        return "indexed", ft.Colors.GREEN_600, ft.Colors.WHITE
    if stage == "converted":
        return "pdf ready", ft.Colors.GREEN_600, ft.Colors.WHITE
    if stage == "downloaded":
        return "converting", ft.Colors.AMBER_700, ft.Colors.WHITE
    return "downloading", ft.Colors.AMBER_700, ft.Colors.WHITE


def _extraction_value(ext: object) -> str:
    """Pick the first non-None value from an extraction object."""
    for attr in ("value_text", "value_numeric", "value_boolean"):
        v = getattr(ext, attr, None)
        if v is not None:
            return str(v)
    return ""


def _close_dialog(page: Any) -> None:
    if hasattr(page, "pop_dialog"):
        page.pop_dialog()
    elif page.dialog:
        page.dialog.open = False
        page.update()


def _get_page(e: Any) -> Any | None:
    return getattr(e, "page", None) or getattr(e.control, "page", None)


def _format_timestamp(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    text = str(value)
    if "T" in text:
        return text.replace("T", " ")[:19]
    return text


@dataclass
class PaperDetailScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            value="View details for an imported paper by ID.",
            color=ft.Colors.GREY_700,
        )
        paper_id_input = ft.TextField(label="Paper ID", width=300)
        content_area = ft.Column([], expand=True, scroll=ft.ScrollMode.AUTO)
        status_bar = ft.Text(value="", size=12)

        def on_load(_: ft.ControlEvent) -> None:
            paper_id = paper_id_input.value or ""
            list_paper = self.services.list_paper
            list_runs = self.services.list_runs
            list_extractions = self.services.list_extractions

            paper = list_paper(paper_id)
            if paper is None:
                content_area.controls = [ft.Text(value="Paper not found")]
                content_area.update()
                return

            title = paper.get("title") or "Untitled"
            year = str(paper.get("year") or "n/a")
            venue = paper.get("venue") or "n/a"
            authors = _format_authors(paper.get("authors_json"))
            abstract = paper.get("abstract") or "No abstract available."
            pipeline_stage = paper.get("pipeline_stage", "imported")
            pipeline_health = paper.get("pipeline_health", "ok")
            last_error = paper.get("last_error_message")

            # --- Status chip ---
            label, bg, fg = _status_info(pipeline_stage, pipeline_health)
            status_chip = _build_chip(label, bgcolor=bg, text_color=fg)

            # --- Metadata section ---
            meta_controls: list[ft.Control] = [
                ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
                ft.Text(authors, size=12, color=ft.Colors.GREY_700),
                ft.Row(
                    [
                        _build_chip(f"Venue: {venue}"),
                        _build_chip(f"Year: {year}"),
                        _build_chip(f"Stage: {pipeline_stage}"),
                        _build_chip(
                            f"Health: {pipeline_health}",
                            bgcolor=ft.Colors.RED_100
                            if pipeline_health == "error"
                            else ft.Colors.GREEN_100,
                        ),
                        status_chip,
                    ],
                    spacing=8,
                ),
                ft.Text(abstract, max_lines=5, overflow=ft.TextOverflow.ELLIPSIS),
            ]

            if pipeline_health == "error":
                error_msg = last_error or "Pipeline error"
                meta_controls.append(
                    ft.Text(value=f"Error: {error_msg}", color=ft.Colors.RED_700, size=12)
                )

            # --- Action menu ---
            enqueue_job = getattr(self.services, "enqueue_job", None)
            delete_paper_fn = getattr(self.services, "delete_paper", None)
            reset_stage_fn = getattr(self.services, "reset_pipeline_stage", None)
            get_markdown = getattr(self.services, "get_paper_markdown", None)

            menu_items: list[ft.PopupMenuItem] = []

            if get_markdown is not None:

                def _on_view_markdown(e: ft.ControlEvent) -> None:
                    page = _get_page(e)
                    if page is None:
                        return
                    md_content = get_markdown(paper_id)
                    body: ft.Control
                    if md_content:
                        body = ft.Markdown(
                            md_content,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            expand=True,
                        )
                    else:
                        body = ft.Text(value="No markdown available.", italic=True)
                    dialog = ft.AlertDialog(
                        title=ft.Text(title),
                        content=ft.Container(
                            width=800,
                            height=600,
                            content=ft.Column([body], scroll=ft.ScrollMode.AUTO, expand=True),
                        ),
                        actions=[ft.TextButton("Close", on_click=lambda _: _close_dialog(page))],
                    )
                    if hasattr(page, "show_dialog"):
                        page.show_dialog(dialog)
                    else:
                        page.dialog = dialog
                        dialog.open = True
                        page.update()

                menu_items.append(
                    ft.PopupMenuItem(
                        content=ft.Text(value="View Markdown"), on_click=_on_view_markdown
                    )
                )

            job_type = _next_job_type(pipeline_stage)
            if job_type is not None and enqueue_job is not None:
                _jt = job_type  # capture for closure

                def _on_retry(_: ft.ControlEvent) -> None:
                    enqueue_job(_jt, paper_id, None, {})
                    status_bar.value = f"Enqueued {_jt} for {title[:50]}"
                    status_bar.update()

                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Retry"), on_click=_on_retry)
                )

            if pipeline_stage not in (None, "imported") and enqueue_job is not None:

                def _on_redownload(_: ft.ControlEvent) -> None:
                    enqueue_job("download", paper_id, None, {})
                    status_bar.value = f"Enqueued re-download for {title[:50]}"
                    status_bar.update()

                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Re-download"), on_click=_on_redownload)
                )

            if pipeline_stage not in (None, "imported") and reset_stage_fn is not None:

                def _on_reset(_: ft.ControlEvent) -> None:
                    reset_stage_fn(paper_id, "imported")
                    status_bar.value = f"Reset {title[:50]} to imported"
                    status_bar.update()

                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Reset"), on_click=_on_reset)
                )

            if delete_paper_fn is not None:

                def _on_delete(e: ft.ControlEvent) -> None:
                    page = _get_page(e)
                    if page is None:
                        return
                    dialog = ft.AlertDialog(
                        title=ft.Text(value="Delete paper?"),
                        content=ft.Text(value=f"This will permanently delete '{title[:80]}'."),
                        actions=[
                            ft.TextButton(
                                "Cancel",
                                on_click=lambda _: _close_dialog(page),
                            ),
                            ft.TextButton(
                                "Delete",
                                on_click=lambda _: (
                                    delete_paper_fn(paper_id),
                                    _close_dialog(page),
                                ),
                            ),
                        ],
                    )
                    if hasattr(page, "show_dialog"):
                        page.show_dialog(dialog)
                    else:
                        page.dialog = dialog
                        dialog.open = True
                        page.update()

                menu_items.append(
                    ft.PopupMenuItem(content=ft.Text(value="Delete"), on_click=_on_delete)
                )

            if menu_items:
                meta_controls.append(
                    ft.Row([ft.PopupMenuButton(items=menu_items, content=ft.Text(value="Actions"))])
                )

            # Card border colour
            if pipeline_health == "error":
                card_border = ft.Border.all(2, ft.Colors.RED_400)
            elif pipeline_stage in ("converted", "embedded", "analyzed"):
                card_border = ft.Border.all(2, ft.Colors.GREEN_600)
            else:
                card_border = ft.Border.all(2, ft.Colors.AMBER_400)

            metadata_card = ft.Card(
                content=ft.Container(
                    padding=10,
                    border=card_border,
                    border_radius=8,
                    content=ft.Column(meta_controls, spacing=6),
                )
            )

            # --- Runs section ---
            runs = list_runs(paper_id)
            runs_controls: list[ft.Control] = []
            if runs:
                runs_controls.append(
                    ft.Text(value="Analysis Runs", size=14, weight=ft.FontWeight.BOLD)
                )
                runs_controls.append(
                    ft.Row(
                        [
                            ft.Text(value="Run ID", width=190, size=11, weight=ft.FontWeight.BOLD),
                            ft.Text(value="Status", width=95, size=11, weight=ft.FontWeight.BOLD),
                            ft.Text(value="Model", width=140, size=11, weight=ft.FontWeight.BOLD),
                            ft.Text(value="Started", width=170, size=11, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                value="Finished", width=170, size=11, weight=ft.FontWeight.BOLD
                            ),
                            ft.Text(value="Tokens", width=120, size=11, weight=ft.FontWeight.BOLD),
                            ft.Text(value="Cost", width=90, size=11, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=8,
                    )
                )
                for run in runs:
                    started_at = _format_timestamp(run.get("started_at"))
                    finished_at = _format_timestamp(run.get("finished_at"))
                    runs_controls.append(
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            content=ft.Row(
                                [
                                    ft.Text(
                                        run.get("run_id", ""),
                                        weight=ft.FontWeight.BOLD,
                                        size=12,
                                        width=190,
                                    ),
                                    _build_chip(run.get("status", "")),
                                    ft.Text(run.get("model_name", ""), size=12, width=140),
                                    ft.Text(started_at, size=11, width=170),
                                    ft.Text(finished_at, size=11, width=170),
                                    ft.Text(
                                        value=(
                                            f"{run.get('tokens_in', 0)}/{run.get('tokens_out', 0)}"
                                        ),
                                        size=11,
                                        width=120,
                                    ),
                                    ft.Text(
                                        value=f"${run.get('cost_usd', 0):.4f}", size=11, width=90
                                    ),
                                ],
                                spacing=8,
                            ),
                        )
                    )
            else:
                runs_controls.append(ft.Text(value="No analysis runs.", italic=True, size=12))

            # --- Extractions section ---
            extractions = list_extractions(paper_id, None)
            ext_controls: list[ft.Control] = []
            ext_controls.append(
                ft.Text(value="Extracted Fields", size=14, weight=ft.FontWeight.BOLD)
            )
            if extractions:
                prompt_versions = sorted(
                    {
                        str(getattr(ext, "prompt_version_id", "")).strip()
                        for ext in extractions
                        if str(getattr(ext, "prompt_version_id", "")).strip()
                    }
                )
                selected_prompt: dict[str, str] = {"value": "all"}
                extraction_rows = ft.Column(spacing=6)

                def _render_extractions() -> None:
                    selected = selected_prompt["value"]
                    filtered = extractions
                    if selected != "all":
                        filtered = [
                            ext
                            for ext in extractions
                            if str(getattr(ext, "prompt_version_id", "")).strip() == selected
                        ]
                    extraction_rows.controls = []
                    if not filtered:
                        extraction_rows.controls.append(
                            ft.Text(
                                value="No extracted fields for selected prompt version.",
                                italic=True,
                                size=12,
                            )
                        )
                    else:
                        for ext in filtered:
                            field_path = getattr(ext, "field_path", "")
                            value = _extraction_value(ext)
                            prompt_version_id = str(getattr(ext, "prompt_version_id", "n/a"))
                            extraction_rows.controls.append(
                                ft.Row(
                                    [
                                        ft.Text(
                                            field_path,
                                            weight=ft.FontWeight.BOLD,
                                            size=12,
                                            width=220,
                                        ),
                                        ft.Text(value, size=12, expand=True),
                                        _build_chip(f"Prompt: {prompt_version_id}"),
                                    ],
                                    spacing=12,
                                )
                            )
                    try:
                        extraction_rows.update()
                    except Exception:
                        pass

                if prompt_versions:
                    prompt_selector = ft.Dropdown(
                        label="Prompt version",
                        value="all",
                        width=240,
                        options=[ft.dropdown.Option("all", "All")]
                        + [ft.dropdown.Option(version, version) for version in prompt_versions],
                    )

                    def _on_prompt_change(e: ft.ControlEvent) -> None:
                        selected_prompt["value"] = str(e.control.value or "all")
                        _render_extractions()

                    prompt_selector.on_select = _on_prompt_change
                    ext_controls.append(prompt_selector)
                _render_extractions()
                ext_controls.append(extraction_rows)
            else:
                ext_controls.append(ft.Text(value="No extracted fields.", italic=True, size=12))

            content_area.controls = [
                metadata_card,
                *runs_controls,
                *ext_controls,
            ]
            content_area.update()

        return ft.Column(
            [
                instructions,
                ft.Row(
                    [
                        paper_id_input,
                        ft.Button(
                            "Load",
                            on_click=on_load,
                            tooltip="Load paper details.",
                        ),
                    ]
                ),
                status_bar,
                content_area,
            ],
            expand=True,
        )
