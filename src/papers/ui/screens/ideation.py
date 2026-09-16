from __future__ import annotations

import json
from dataclasses import dataclass

import flet as ft

from papers.ui.errors import public_ui_error


def _integer(field: ft.TextField, label: str) -> int:
    try:
        return int(str(field.value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer.") from exc


@dataclass
class IdeationScreen:
    services: object

    def build(self) -> ft.Control:
        project_id = ft.TextField(label="Project id", expand=True)
        question = ft.TextField(label="Project-wide question", expand=True)
        profile = ft.TextField(label="Profile override", width=180, value="")
        model = ft.TextField(label="Model override", width=180, value="")
        critic_model = ft.TextField(label="Critic model override", width=180, value="")
        max_papers = ft.TextField(label="Max papers", value="12", width=120)
        excerpt_bytes = ft.TextField(label="Excerpt bytes", value="1200", width=140)
        max_excerpts = ft.TextField(label="Excerpts/paper", value="6", width=140)
        timeout = ft.TextField(label="Timeout seconds", value="300", width=140)
        max_tokens = ft.TextField(label="Max tokens", value="8000", width=140)
        bundle = ft.TextField(label="Verified ideation bundle", expand=True)
        idea_id = ft.TextField(label="Idea id", expand=True)
        plan_profile = ft.TextField(label="Profile override", width=180, value="")
        plan_model = ft.TextField(label="Model override", width=180, value="")
        plan_timeout = ft.TextField(label="Timeout seconds", value="300", width=140)
        plan_tokens = ft.TextField(label="Max tokens", value="8000", width=140)
        selection_note = ft.TextField(
            label="Selection note", value="operator-selected draft idea", expand=True
        )
        output = ft.Text(value="", selectable=True)

        def ideate(_: ft.ControlEvent) -> None:
            operation = getattr(self.services, "ideate_project", None)
            if not str(project_id.value or "").strip() or not str(question.value or "").strip():
                output.value = "Project id and question are required."
            elif operation is None:
                output.value = "Project ideation is not configured."
            else:
                try:
                    result = operation(
                        project_id=str(project_id.value).strip(),
                        question=str(question.value).strip(),
                        profile_id=str(profile.value or "").strip() or None,
                        model=str(model.value or "").strip() or None,
                        critic_model=str(critic_model.value or "").strip() or None,
                        max_papers=_integer(max_papers, "Max papers"),
                        excerpt_bytes=_integer(excerpt_bytes, "Excerpt bytes"),
                        max_excerpts_per_paper=_integer(max_excerpts, "Excerpts per paper"),
                        timeout_s=_integer(timeout, "Timeout"),
                        max_tokens=_integer(max_tokens, "Max tokens"),
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        def plan(_: ft.ControlEvent) -> None:
            operation = getattr(self.services, "plan_idea", None)
            if not str(bundle.value or "").strip() or not str(idea_id.value or "").strip():
                output.value = "Verified bundle path and idea id are required."
            elif operation is None:
                output.value = "Idea planning is not configured."
            else:
                try:
                    result = operation(
                        bundle_path=str(bundle.value).strip(),
                        idea_id=str(idea_id.value).strip(),
                        profile_id=str(plan_profile.value or "").strip() or None,
                        model=str(plan_model.value or "").strip() or None,
                        timeout_s=_integer(plan_timeout, "Timeout"),
                        max_tokens=_integer(plan_tokens, "Max tokens"),
                        selection_note=str(selection_note.value or "").strip(),
                    )
                    output.value = json.dumps(result, indent=2, default=str)
                except Exception as exc:
                    output.value = f"Error: {public_ui_error(exc)}"
            output.update()

        ideate_form = ft.Column(
            [
                ft.Row([project_id, question], wrap=True),
                ft.Row([profile, model, critic_model], wrap=True),
                ft.Row(
                    [
                        max_papers,
                        excerpt_bytes,
                        max_excerpts,
                        timeout,
                        max_tokens,
                        ft.Button("Ideate project", on_click=ideate),
                    ],
                    wrap=True,
                ),
            ],
            spacing=8,
        )
        plan_form = ft.Column(
            [
                ft.Row([bundle, idea_id], wrap=True),
                ft.Row([plan_profile, plan_model, plan_timeout, plan_tokens], wrap=True),
                ft.Row([selection_note, ft.Button("Plan selected idea", on_click=plan)], wrap=True),
            ],
            spacing=8,
        )
        return ft.Column(
            [
                ft.Text(value="Project Ideation", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    value=(
                        "Generate bounded, evidence-linked ideas, then plan one explicit "
                        "selection. "
                        "This does not execute or approve an investigation."
                    ),
                    color=ft.Colors.GREY_700,
                    size=12,
                    data="non-authorizing",
                ),
                ideate_form,
                plan_form,
                output,
            ],
            expand=True,
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )
