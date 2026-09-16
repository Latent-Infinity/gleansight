from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


@dataclass
class ProjectScreen:
    services: object

    def build(self) -> ft.Control:
        projection = ft.TextField(label="Projection path", expand=True)
        manifest = ft.TextField(label="Approval manifest path", expand=True)
        digest = ft.TextField(label="Approved digest", expand=True)
        confirmation = ft.TextField(label="Type APPROVE", width=160)
        output = ft.Text(value="", selectable=True)

        def project(_: ft.ControlEvent) -> None:
            projector = getattr(self.services, "project_records", None)
            projection_path = str(projection.value or "").strip()
            manifest_path = str(manifest.value or "").strip()
            if not projection_path or not manifest_path:
                output.value = "Projection path and approval manifest path are required."
            elif projector is None:
                output.value = "Project is not configured."
            else:
                try:
                    result = projector(
                        projection_path=projection_path,
                        manifest_path=manifest_path,
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        def approve(_: ft.ControlEvent) -> None:
            approver = getattr(self.services, "approve_digest", None)
            digest_value = str(digest.value or "").strip()
            if not digest_value:
                output.value = "Digest is required."
            elif str(confirmation.value or "").strip() != "APPROVE":
                output.value = "Type APPROVE to confirm this authority-sensitive action."
            elif approver is None:
                output.value = "Approve digest is not configured."
            else:
                try:
                    result = approver(digest=digest_value)
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        return ft.Column(
            [
                ft.Text(value="Project", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value="Admit a human-approved projection, or persist an approved digest.",
                    color=ft.Colors.GREY_700,
                    size=12,
                ),
                ft.Column(
                    [
                        ft.Row(
                            [projection, manifest, ft.Button("Project", on_click=project)],
                            wrap=True,
                        ),
                        ft.Row(
                            [digest, confirmation, ft.Button("Approve digest", on_click=approve)],
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
