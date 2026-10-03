from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import flet as ft
from pydantic import TypeAdapter

from gleansight.api.models import OperationError
from papers.domain.errors import BaseModuleError
from papers.domain.idea_reviews import IdeaBinding, IdeaReview, ReviewBundleSummary, ReviewDesk
from papers.ui.errors import public_ui_error

if TYPE_CHECKING:
    from papers.ui.app import UIServices


@dataclass(frozen=True, slots=True)
class IdeaReviewDesk:
    services: UIServices
    bundle: ft.TextField
    idea_id: ft.TextField
    review_id: ft.TextField
    project_id: ft.TextField

    def build(self) -> ft.Control:
        selected: IdeaBinding | None = None
        previous: str | None = None
        choices = ft.Dropdown(label="Project idea bundles", width=320, options=[])
        ideas = ft.Dropdown(label="Idea to inspect", width=320, options=[])
        reviewer = ft.TextField(label="Researcher name", width=320)
        verdict = ft.Dropdown(
            label="Researcher decision",
            value="keep",
            width=180,
            options=[
                ft.DropdownOption(key=value, text=value.title())
                for value in ("keep", "revise", "reject")
            ],
        )
        rationale = ft.TextField(label="Decision rationale", multiline=True, min_lines=2)
        details = ft.Column(spacing=8)
        status = ft.Text(
            "Load a verified bundle to inspect its evidence and critique.", selectable=True
        )
        desk: ReviewDesk | None = None

        def show_idea() -> None:
            nonlocal selected, previous
            if desk is None:
                return
            item = next((item for item in desk.ideas if item.idea.idea_id == ideas.value), None)
            if item is None:
                return
            selected = item.binding
            previous = item.reviews[-1].review_id if item.reviews else None
            self.idea_id.value = item.idea.idea_id
            self.review_id.value = previous or ""
            details.controls = [
                ft.Text(f"{item.idea.title} · {item.state}", weight=ft.FontWeight.BOLD),
                ft.Text(item.idea.falsifiable_question, selectable=True),
                ft.Text(f"Gap: {item.idea.gap}", selectable=True),
                ft.Text(f"Mechanism: {item.idea.mechanism}", selectable=True),
                ft.Text(
                    f"Feasibility uncertainty: {item.idea.feasibility_uncertainty}", selectable=True
                ),
                ft.Text(f"Smallest test: {item.idea.smallest_test}", selectable=True),
                ft.Text(
                    f"Model critique: {item.critique.verdict.value} — {item.critique.rationale}",
                    selectable=True,
                ),
                ft.Text(f"Critique uncertainty: {item.critique.uncertainty}", selectable=True),
                ft.Text(f"Bundle SHA256: {item.binding.bundle_sha256}", size=12, selectable=True),
                ft.Text(f"Idea SHA256: {item.binding.idea_sha256}", size=12, selectable=True),
                ft.Text("Frozen supporting evidence", weight=ft.FontWeight.BOLD),
            ]
            for label, value in (
                ("Known overlap", item.idea.known_overlap),
                ("Data assumptions", item.idea.data_assumptions),
                ("Model assumptions", item.idea.model_assumptions),
                ("Compute assumptions", item.idea.compute_assumptions),
                ("Critique overlap", item.critique.overlap),
                ("Contradiction", item.critique.contradiction),
            ):
                if value:
                    details.controls.append(ft.Text(f"{label}: {value}", selectable=True))
            for excerpt in item.evidence:
                details.controls.extend(
                    [
                        ft.Text(
                            f"{excerpt.title} · {excerpt.section} · {excerpt.excerpt_id}", size=12
                        ),
                        ft.Text(excerpt.quote, selectable=True),
                    ]
                )
            details.controls.append(ft.Text("Immutable review history", weight=ft.FontWeight.BOLD))
            for review in item.reviews:
                stale = (
                    " · stale source identity" if review.review_id in item.stale_review_ids else ""
                )
                details.controls.append(
                    ft.Text(
                        f"Revision {review.revision}: {review.verdict} · {review.reviewer} · "
                        f"{review.created_at}{stale}\n{review.rationale}",
                        selectable=True,
                    )
                )
            for selection in item.selections:
                details.controls.append(
                    ft.Text(
                        f"Selected plan: {selection.plan_bundle}\nReview: {selection.review_id}",
                        selectable=True,
                    )
                )
            self.idea_id.update()
            self.review_id.update()
            details.update()

        def load(_: ft.Event[ft.Button] | None = None) -> None:
            nonlocal desk, selected, previous
            operation = getattr(self.services, "review_ideas", None)
            if operation is None:
                status.value = "Idea review is not configured."
            else:
                try:
                    desk = ReviewDesk.model_validate(
                        operation(bundle_path=str(self.bundle.value or "").strip())
                    )
                    ideas.options = [
                        ft.DropdownOption(key=item.idea.idea_id, text=item.idea.title)
                        for item in desk.ideas
                    ]
                    ideas.value = (
                        self.idea_id.value
                        if any(item.idea.idea_id == self.idea_id.value for item in desk.ideas)
                        else (desk.ideas[0].idea.idea_id if desk.ideas else None)
                    )
                    status.value = (
                        f"Verified frozen bundle · {desk.project_id} · {len(desk.ideas)} idea(s)"
                    )
                    ideas.update()
                    show_idea()
                except (ValueError, OSError, RuntimeError, OperationError, BaseModuleError) as exc:
                    desk, selected, previous = None, None, None
                    self.review_id.value = ""
                    self.review_id.update()
                    details.controls.clear()
                    details.update()
                    status.value = f"Error: {public_ui_error(exc)}"
            status.update()

        def browse(_: ft.Event[ft.Button]) -> None:
            operation = getattr(self.services, "list_idea_bundles", None)
            if operation is None:
                status.value = "Bundle browsing is not configured."
            else:
                try:
                    result = operation(project_id=str(self.project_id.value or "").strip() or None)
                    bundles = TypeAdapter(tuple[ReviewBundleSummary, ...]).validate_python(
                        result["bundles"]
                    )
                    choices.options = [
                        ft.DropdownOption(
                            key=str(item.bundle_path),
                            text=f"{item.bundle_path.name} · {item.state}",
                        )
                        for item in bundles
                    ]
                    status.value = f"Found {len(bundles)} project idea bundle(s)."
                    choices.update()
                except (ValueError, OSError, RuntimeError, OperationError, BaseModuleError) as exc:
                    status.value = f"Error: {public_ui_error(exc)}"
            status.update()

        def choose_bundle(_: ft.Event[ft.Dropdown]) -> None:
            self.bundle.value = choices.value or ""
            self.bundle.update()
            load()

        def record(_: ft.Event[ft.Button]) -> None:
            operation = getattr(self.services, "record_idea_review", None)
            if selected is None:
                status.value = "Inspect an idea before recording a review."
            elif operation is None:
                status.value = "Idea review is not configured."
            else:
                try:
                    saved = IdeaReview.model_validate(
                        operation(
                            binding=selected.model_dump(mode="json"),
                            reviewer=str(reviewer.value or "").strip(),
                            verdict=str(verdict.value or ""),
                            rationale=str(rationale.value or "").strip(),
                            previous_review_id=previous,
                        )
                    )
                    load()
                    status.value = (
                        f"Recorded immutable revision {saved.revision} · {saved.verdict}. "
                        "No execution or NSQD approval granted."
                    )
                except (ValueError, OSError, RuntimeError, OperationError, BaseModuleError) as exc:
                    status.value = f"Error: {public_ui_error(exc)}"
            status.update()

        ideas.on_select = lambda _: show_idea()
        choices.on_select = choose_bundle
        return ft.Column(
            [
                ft.Text("Researcher review desk", weight=ft.FontWeight.BOLD),
                ft.Row([choices, ft.Button("Browse project bundles", on_click=browse)], wrap=True),
                ft.Row([ft.Button("Inspect idea bundle", on_click=load), ideas], wrap=True),
                status,
                details,
                ft.Row([reviewer, verdict], wrap=True),
                rationale,
                ft.Button("Record researcher decision", on_click=record),
                ft.Text(
                    "Researcher decisions do not verify evidence, authorize execution, "
                    "or activate NSQD operators.",
                    size=12,
                ),
            ],
            spacing=8,
        )
