from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error

_TAU_ACTIONS = frozenset({"export", "inventory", "review", "evaluate"})


def _parse_hashes(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(",", " ").split() if item.strip()]


@dataclass
class TauScreen:
    services: object

    def build(self) -> ft.Control:
        hashes = ft.TextField(label="Candidate artifact hashes", expand=True)
        action = ft.TextField(label="Action", value="export", width=120)
        output_path = ft.TextField(label="Output path", width=180)
        inputs = ft.TextField(label="Review input paths", width=180)
        balanced = ft.TextField(label="Require balanced", value="false", width=140)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            command = getattr(self.services, "tau_command", None)
            hash_list = _parse_hashes(str(hashes.value or ""))
            action_id = str(action.value or "").strip().lower()
            if not hash_list:
                output.value = "Candidate artifact hashes are required."
            elif action_id not in _TAU_ACTIONS:
                output.value = "Action must be export, inventory, review, or evaluate."
            elif action_id == "evaluate" and not _parse_hashes(str(inputs.value or "")):
                output.value = "Evaluate requires at least one review input path."
            elif command is None:
                output.value = "Tau commands are not configured."
            else:
                try:
                    result = command(
                        hashes=hash_list,
                        action=action_id,
                        output_path=str(output_path.value or "").strip() or None,
                        input_paths=_parse_hashes(str(inputs.value or "")),
                        require_balanced=str(balanced.value or "").strip().lower()
                        in {"1", "true", "yes"},
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Tau", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value=(
                        "Export or inventory measurements, or produce report-only autonomous tau "
                        "review evidence. These actions do not activate a threshold or operator."
                    ),
                    color=ft.Colors.GREY_700,
                    size=12,
                    data="report-only-non-authorizing",
                ),
                ft.Column(
                    [
                        hashes,
                        ft.Row(
                            [
                                action,
                                output_path,
                                inputs,
                                balanced,
                                ft.Button("Run", on_click=run),
                            ],
                            wrap=True,
                        ),
                    ],
                    spacing=8,
                ),
                output,
            ],
            expand=True,
            spacing=12,
        )
