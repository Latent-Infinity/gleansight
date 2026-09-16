from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error

_RUNTIME_OPERATORS = frozenset({"A", "B"})


@dataclass
class DivergeScreen:
    services: object

    def build(self) -> ft.Control:
        fixture = ft.TextField(label="Candidate fixture path", expand=True)
        axiom = ft.TextField(label="Axiom", expand=True)
        snapshot = ft.TextField(label="Snapshot id", expand=True)
        policy = ft.TextField(label="Domain policy id", value="finance/1", width=180)
        operator = ft.TextField(label="Operator", value="A", width=80)
        target = ft.TextField(label="Target cell id", width=180)
        axiom_cell = ft.TextField(label="Axiom cell id", width=180)
        state = ft.TextField(label="Snapshot state", value="calibration", width=140)
        output = ft.Text(value="", selectable=True)

        def run(_: ft.ControlEvent) -> None:
            diverge = getattr(self.services, "diverge_candidate", None)
            fixture_path = str(fixture.value or "").strip()
            axiom_text = str(axiom.value or "").strip()
            snapshot_id = str(snapshot.value or "").strip()
            operator_id = str(operator.value or "").strip().upper()
            target_cell_id = str(target.value or "").strip() or None
            axiom_cell_id = str(axiom_cell.value or "").strip() or None
            if not fixture_path or not axiom_text or not snapshot_id:
                output.value = "Fixture path, axiom, and snapshot id are required."
            elif operator_id not in _RUNTIME_OPERATORS:
                output.value = "Operator must be A or B."
            elif operator_id == "B" and (target_cell_id is None or axiom_cell_id is None):
                output.value = "Operator B requires target cell id and axiom cell id."
            elif diverge is None:
                output.value = "Diverge is not configured."
            else:
                try:
                    result = diverge(
                        candidate_fixture=fixture_path,
                        axiom=axiom_text,
                        snapshot_id=snapshot_id,
                        domain_policy_id=str(policy.value or "").strip(),
                        operator=operator_id,
                        target_cell_id=target_cell_id,
                        axiom_cell_id=axiom_cell_id,
                        snapshot_state=str(state.value or "").strip(),
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Diverge", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Generate a candidate with Operator A, or composition-gated Operator B.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Column(
                    [
                        ft.Row([fixture, axiom, snapshot, policy], wrap=True),
                        ft.Row(
                            [
                                operator,
                                target,
                                axiom_cell,
                                state,
                                ft.Button("Diverge", on_click=run),
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
