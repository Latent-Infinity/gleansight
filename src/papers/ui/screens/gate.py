from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class GateScreen:
    services: object

    def build(self) -> ft.Control:
        hash_input = ft.TextField(label="Candidate artifact hash", expand=True)
        snapshot = ft.TextField(label="Snapshot id", expand=True)
        version = ft.TextField(label="Corpus version", width=140)
        evaluator = ft.TextField(label="Evaluator run id", width=180)
        state = ft.TextField(label="Snapshot state", value="calibration", width=160)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            gate = getattr(self.services, "gate_candidate", None)
            artifact_hash = str(hash_input.value or "").strip()
            snapshot_id = str(snapshot.value or "").strip()
            version_text = str(version.value or "").strip()
            evaluator_run_id = str(evaluator.value or "").strip()
            if not artifact_hash or not snapshot_id or not version_text or not evaluator_run_id:
                output.value = (
                    "Candidate hash, snapshot id, corpus version, "
                    "and evaluator run id are required."
                )
            elif gate is None:
                output.value = "Gate is not configured."
            else:
                try:
                    result = gate(
                        candidate_artifact_hash=artifact_hash,
                        snapshot_id=snapshot_id,
                        corpus_version=int(version_text),
                        evaluator_run_id=evaluator_run_id,
                        snapshot_state=str(state.value or "").strip(),
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Gate", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Score a persisted candidate under a new evaluator run id.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row(
                    [
                        hash_input,
                        snapshot,
                        version,
                        evaluator,
                        state,
                        ft.Button("Gate", on_click=run),
                    ],
                    wrap=True,
                ),
                output,
            ],
            expand=True,
            spacing=12,
        )
