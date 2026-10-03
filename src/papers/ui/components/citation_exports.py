"""Query export controls using the existing Flet form primitives."""

from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft
from pydantic import ValidationError as ModelValidationError

from papers.app.use_cases.citation_exports import ExportPapersUseCase
from papers.domain.citations import ExportSelection
from papers.domain.errors import BaseModuleError


@dataclass
class CitationExportControls:
    use_case: ExportPapersUseCase | None
    status: Callable[[str, bool], None]
    selected_ids: set[str] = field(default_factory=set)

    def checkbox(self, paper_id: str) -> ft.Checkbox:
        def select(event: ft.Event[ft.Checkbox]) -> None:
            if event.control.value:
                self.selected_ids.add(paper_id)
            else:
                self.selected_ids.discard(paper_id)

        return ft.Checkbox(label="Select for export", value=False, on_change=select)

    def build(self) -> ft.Control:
        format_input = ft.Dropdown(
            label="Export format",
            value="bibtex",
            width=170,
            options=[
                ft.dropdown.Option(key, label)
                for key, label in (
                    ("bibtex", "BibTeX"),
                    ("ris", "RIS"),
                    ("csv", "Metadata CSV"),
                    ("extractions", "Extraction JSON"),
                )
            ],
        )
        scope_input = ft.Dropdown(
            label="Export scope",
            value="selected",
            width=210,
            options=[
                ft.dropdown.Option("selected", "Selected results"),
                ft.dropdown.Option("project", "Whole project"),
            ],
        )
        project_input = ft.TextField(label="Project ID (whole project scope)", width=290)

        def export(_: ft.Event[ft.OutlinedButton]) -> None:
            if self.use_case is None:
                self.status("Export service is unavailable.", True)
                return
            if scope_input.value == "selected" and not self.selected_ids:
                self.status("Select at least one result to export.", True)
                return
            if scope_input.value == "project" and not (project_input.value or "").strip():
                self.status("Enter the project ID to export.", True)
                return
            try:
                selection = ExportSelection.model_validate(
                    {
                        "paper_ids": sorted(self.selected_ids)
                        if scope_input.value == "selected"
                        else [],
                        "project_id": (project_input.value or "").strip()
                        if scope_input.value == "project"
                        else None,
                        "format": format_input.value,
                    }
                )
                result = self.use_case.execute(selection)
            except (BaseModuleError, ModelValidationError, OSError) as exc:
                self.status(f"Export failed: {exc}", True)
                return
            self.status(
                f"Export saved: {result.artifact_path}; manifest: {result.manifest_path}", False
            )

        return ft.Column(
            [
                ft.Row(
                    [
                        format_input,
                        scope_input,
                        project_input,
                        ft.OutlinedButton("Export selection / project", on_click=export),
                    ],
                    wrap=True,
                ),
                ft.Text(
                    "Exports are immutable snapshots. Missing metadata and passage locators "
                    "are recorded explicitly in the export manifest and extraction JSON.",
                    size=12,
                ),
            ]
        )
