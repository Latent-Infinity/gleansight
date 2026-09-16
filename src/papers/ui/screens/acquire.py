from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class AcquireScreen:
    services: object

    def build(self) -> ft.Control:
        snapshot = ft.TextField(label="Snapshot id", expand=True)
        policy = ft.TextField(label="Domain policy id", value="finance/1", width=180)
        target = ft.TextField(label="Target", value="calibration", width=140)
        decision = ft.TextField(label="Human decision", width=180)
        max_jobs = ft.TextField(label="Max paper jobs", value="1", width=140)
        output = ft.Text(value="", selectable=True)

        def acquire(_: ft.ControlEvent) -> None:
            acquirer = getattr(self.services, "acquire_corpus", None)
            snapshot_id = str(snapshot.value or "").strip()
            if not snapshot_id:
                output.value = "Snapshot id is required."
            elif acquirer is None:
                output.value = "Acquire is not configured."
            else:
                try:
                    human_decision = str(decision.value or "").strip() or None
                    result = acquirer(
                        snapshot_id=snapshot_id,
                        domain_policy_id=str(policy.value or "").strip(),
                        target=str(target.value or "").strip(),
                        human_decision=human_decision,
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        def run_jobs(_: ft.ControlEvent) -> None:
            runner = getattr(self.services, "run_paper_jobs", None)
            if runner is None:
                output.value = "Paper jobs are not configured."
            else:
                try:
                    result = runner(max_jobs=int(str(max_jobs.value or "1").strip() or "1"))
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Acquire", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Run insufficiency acquisition, then process paper jobs.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Column(
                    [
                        ft.Row(
                            [
                                snapshot,
                                policy,
                                target,
                                decision,
                                ft.Button("Acquire", on_click=acquire),
                            ],
                            wrap=True,
                        ),
                        ft.Row(
                            [max_jobs, ft.Button("Run paper jobs", on_click=run_jobs)], wrap=True
                        ),
                    ],
                    spacing=8,
                ),
                output,
            ],
            expand=True,
            spacing=12,
        )
