from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class GroundScreen:
    services: object

    def build(self) -> ft.Control:
        hash_input = ft.TextField(label="Candidate artifact hash", expand=True)
        snapshot = ft.TextField(label="Snapshot id", expand=True)
        version = ft.TextField(label="Corpus version", width=140)
        state = ft.TextField(label="Snapshot state", value="calibration", width=160)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            ground = getattr(self.services, "ground_candidate", None)
            artifact_hash = str(hash_input.value or "").strip()
            snapshot_id = str(snapshot.value or "").strip()
            version_text = str(version.value or "").strip()
            if not artifact_hash or not snapshot_id or not version_text:
                output.value = "Candidate hash, snapshot id, and corpus version are required."
            elif ground is None:
                output.value = "Ground is not configured."
            else:
                try:
                    result = ground(
                        candidate_artifact_hash=artifact_hash,
                        snapshot_id=snapshot_id,
                        corpus_version=int(version_text),
                        snapshot_state=str(state.value or "").strip(),
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Ground", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Measure prior art against the candidate's domain-policy corpus view.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Row(
                    [hash_input, snapshot, version, state, ft.Button("Ground", on_click=run)],
                    wrap=True,
                ),
                output,
            ],
            expand=True,
            spacing=12,
        )
