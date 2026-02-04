from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass
class PaperDetailScreen:
    services: object

    def build(self) -> ft.Control:
        instructions = ft.Text(
            "View details for an imported paper by ID. Paper IDs come from the import step.",
            color=ft.Colors.GREY_700,
        )
        paper_id_input = ft.TextField(label="Paper ID", width=300)
        metadata = ft.Text("No paper loaded")
        runs_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Run ID")),
                ft.DataColumn(ft.Text("Status")),
            ],
            rows=[],
        )

        def on_load(_: ft.ControlEvent) -> None:
            paper_id = paper_id_input.value or ""
            list_paper = getattr(self.services, "list_paper")
            list_runs = getattr(self.services, "list_runs")
            paper = list_paper(paper_id)
            if paper is None:
                metadata.value = "Paper not found"
                runs_table.rows = []
                return
            metadata.value = f"{paper.get('title', 'Untitled')} ({paper.get('year', 'n/a')})"
            runs = list_runs(paper_id)
            runs_table.rows = [
                ft.DataRow(
                    cells=[ft.DataCell(ft.Text(run["run_id"])), ft.DataCell(ft.Text(run["status"]))]
                )
                for run in runs
            ]

        return ft.Column(
            [
                instructions,
                ft.Row(
                    [
                        paper_id_input,
                        ft.ElevatedButton(
                            "Load",
                            on_click=on_load,
                            tooltip="Load metadata and analysis runs for this paper.",
                        ),
                    ]
                ),
                metadata,
                runs_table,
            ],
            expand=True,
        )
