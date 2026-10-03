from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import flet as ft

from papers.domain.synthesis_grounding import GroundedSource
from papers.ui.errors import public_ui_error
from papers.ui.screens.synthesis_sources import SourcePassage


@dataclass
class SynthesisScreen:
    services: UIServices

    def build(self) -> ft.Control:
        instructions = ft.Text(
            value="Ask a question and get an answer synthesized from your paper corpus.",
            color=ft.Colors.GREY_700,
        )
        list_projects = getattr(self.services, "list_projects", None)
        projects = list_projects() if list_projects is not None else []
        project_scope = ft.Dropdown(
            label="Project scope",
            value="",
            width=320,
            options=[ft.DropdownOption(key="", text="All papers")]
            + [
                ft.DropdownOption(key=str(project["project_id"]), text=str(project["name"]))
                for project in projects
            ],
        )
        question_input = ft.TextField(label="Your Question", width=320)
        answer_display = ft.Markdown(
            "",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )
        sources_display = ft.Column(spacing=4)
        progress_bar = ft.ProgressBar(width=400, visible=False)
        error_text = ft.Text(value="", color=ft.Colors.RED_700)
        status_bar = ft.Text(value="", size=12)

        def _safe_update(control: ft.Control) -> None:
            try:
                control.update()
            except Exception:
                pass

        def _set_status(message: str, is_error: bool = False) -> None:
            status_bar.value = message
            status_bar.color = ft.Colors.RED_700 if is_error else ft.Colors.GREY_700
            _safe_update(status_bar)

        def on_ask(_: ft.Event[ft.TextField] | ft.Event[ft.Button] | None) -> None:
            question = (question_input.value or "").strip()
            if not question:
                error_text.value = "Please enter a question."
                answer_display.value = ""
                sources_display.controls.clear()
                progress_bar.visible = False
                _safe_update(error_text)
                _safe_update(answer_display)
                _safe_update(sources_display)
                _safe_update(progress_bar)
                return

            # Show loading state
            error_text.value = ""
            answer_display.value = ""
            sources_display.controls.clear()
            progress_bar.visible = True
            question_input.read_only = True
            _safe_update(error_text)
            _safe_update(answer_display)
            _safe_update(sources_display)
            _safe_update(progress_bar)
            _safe_update(question_input)

            try:
                synthesize_uc = self.services.synthesize_from_corpus
                answer, sources = synthesize_uc.synthesize(
                    question=question,
                    project_id=project_scope.value or None,
                    llm_model=str(
                        self.services.ui_settings.get("llm_default_model") or "gpt-4o-mini"
                    ),
                )

                answer_display.value = answer
                sources_display.controls = [
                    SourcePassage(
                        GroundedSource.model_validate(s), self.services.get_paper_markdown
                    ).build()
                    for s in sources
                ]
                _set_status(f"Synthesized with {len(sources)} cited passage(s).")
            except Exception as exc:
                error_text.value = f"Error: {public_ui_error(exc)}"
                _set_status("Synthesis failed.", is_error=True)
            finally:
                progress_bar.visible = False
                question_input.read_only = False
                _safe_update(progress_bar)
                _safe_update(question_input)
                _safe_update(answer_display)
                _safe_update(sources_display)
                _safe_update(error_text)

        question_input.on_submit = on_ask

        return ft.Column(
            [
                instructions,
                project_scope,
                ft.Row(
                    [
                        question_input,
                        ft.Button(
                            "Ask",
                            on_click=on_ask,
                            tooltip="Synthesize an answer from your paper corpus.",
                        ),
                    ],
                    wrap=True,
                ),
                progress_bar,
                error_text,
                ft.Text(value="Answer:", weight=ft.FontWeight.BOLD),
                answer_display,
                ft.Divider(),
                ft.Text(value="Sources:", weight=ft.FontWeight.BOLD),
                sources_display,
                status_bar,
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )


if TYPE_CHECKING:
    from papers.ui.app import UIServices
