"""Saved-query and screening controls using the desktop's existing Flet primitives."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import flet as ft
from pydantic import JsonValue, TypeAdapter
from pydantic import ValidationError as ModelValidationError

from papers.domain.errors import BaseModuleError, ValidationError
from papers.domain.screening import (
    ImportSelection,
    ReviewRequest,
    SaveSearch,
    ScheduleRequest,
    SearchFilters,
)
from papers.ui.components.screening_rows import screening_row
from papers.ui.screening_services import ProjectOption, ScreeningService


@dataclass(frozen=True, slots=True)
class ScreeningControls:
    service: ScreeningService | None
    projects: Callable[[], list[dict[str, JsonValue]]]

    def build(self) -> ft.Control:
        service = self.service
        if service is None:
            return ft.Text("Saved discovery is unavailable.", color=ft.Colors.GREY_700)
        status = ft.Text(
            "Save a project query, then rerun it to review new and changed papers.", size=12
        )
        saved_input = ft.Dropdown(label="Saved search", width=300)
        project_input = ft.Dropdown(
            label="Project",
            width=220,
            options=[
                ft.dropdown.Option(item.project_id, item.name)
                for item in TypeAdapter(tuple[ProjectOption, ...]).validate_python(self.projects())
            ],
        )
        name_input = ft.TextField(label="Search name", width=220)
        query_input = ft.TextField(label="Saved query", width=340)
        year_input = ft.TextField(label="Year from", width=130)
        limit_input = ft.TextField(label="Max results", value="50", width=130)
        reviewer_input = ft.TextField(label="Reviewer", width=180)
        rationale_input = ft.TextField(label="Rationale", width=340)
        decision_input = ft.Dropdown(
            label="Decision",
            width=160,
            value="maybe",
            options=[
                ft.dropdown.Option(value, value.title())
                for value in ("include", "exclude", "maybe")
            ],
        )
        tag_input = ft.TextField(label="Tag IDs (optional, comma-separated)", width=340)
        count_input = ft.Dropdown(
            label="Daily reruns",
            width=150,
            value="1",
            options=[ft.dropdown.Option(str(value)) for value in (1, 3, 7)],
        )
        rows = ft.Column(spacing=8)
        selected: set[str] = set()
        displayed_revisions: dict[str, int] = {}
        content = ft.Column(
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            height=320,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        def refresh() -> None:
            if content.parent is not None:
                content.parent.update()

        def attempt(action: Callable[[], str]) -> None:
            try:
                message = action()
                status.value, status.color = message, ft.Colors.GREEN_600
            except ModelValidationError as error:
                fields = ", ".join(
                    " ".join(str(part) for part in item["loc"]).replace("_", " ")
                    for item in error.errors(include_url=False, include_input=False)
                )
                status.value, status.color = f"Please check: {fields}.", ft.Colors.RED_600
            except BaseModuleError as error:
                status.value, status.color = str(error), ft.Colors.RED_600
            refresh()

        def search_id() -> str:
            if not saved_input.value:
                raise ValidationError("Choose a saved search first.")
            return saved_input.value

        def load() -> None:
            saved_input.options = [
                ft.dropdown.Option(item.search_id, item.name) for item in service.list()
            ]
            selected.clear()
            displayed_revisions.clear()
            rows.controls.clear()
            if not saved_input.value:
                rows.controls.append(ft.Text("No search selected."))
                return
            desk = service.get(saved_input.value)
            displayed_revisions.update(
                (review.candidate_id, review.revision) for review in desk.reviews
            )
            project_input.value, name_input.value = desk.search.project_id, desk.search.name
            query_input.value = desk.search.query
            year_input.value = str(desk.search.filters.year_min or "")
            limit_input.value = str(desk.search.max_results)
            observations = {
                item.candidate_id: (run.sequence, item)
                for run in desk.runs
                for item in run.observations
            }
            for sequence, item in observations.values():
                history = tuple(
                    review for review in desk.reviews if review.candidate_id == item.candidate_id
                )
                rows.controls.append(screening_row(item, sequence, history, selected))
            if not observations:
                rows.controls.append(ft.Text("No results yet. Rerun this saved query."))

        def save() -> str:
            request = SaveSearch(
                project_id=project_input.value or "",
                name=name_input.value or "",
                query=query_input.value or "",
                filters=SearchFilters(
                    year_min=TypeAdapter(int).validate_python(year_input.value)
                    if year_input.value
                    else None
                ),
                max_results=TypeAdapter(int).validate_python(limit_input.value),
            )
            saved_input.value = service.save(request).search_id
            load()
            return "Saved query and filters. Rerun when ready."

        def rerun() -> str:
            run = service.rerun(search_id())
            load()
            counts = {
                kind: sum(item.delta == kind for item in run.observations)
                for kind in ("new", "seen", "metadata_changed")
            }
            return (
                f"Run {run.sequence}: {counts['new']} new · {counts['seen']} seen · "
                f"{counts['metadata_changed']} changed."
            )

        def review() -> str:
            if not selected:
                raise ValidationError("Select candidates to record a decision.")
            identifier = search_id()
            for candidate in selected:
                request = ReviewRequest.model_validate(
                    {
                        "search_id": identifier,
                        "candidate_id": candidate,
                        "decision": decision_input.value,
                        "reviewer": reviewer_input.value,
                        "rationale": rationale_input.value,
                        "expected_revision": displayed_revisions.get(candidate, 0),
                    }
                )
                service.review(request)
            load()
            return "Screening revisions saved with reviewer and rationale."

        def import_selected() -> str:
            result = service.import_selected(
                ImportSelection(
                    search_id=search_id(),
                    candidate_ids=tuple(sorted(selected)),
                    tag_ids=tuple(
                        value.strip()
                        for value in (tag_input.value or "").split(",")
                        if value.strip()
                    ),
                )
            )
            return (
                f"Imported {len(result.paper_ids)} inclusion(s) with project and tag attachments."
            )

        def schedule() -> str:
            result = service.schedule(
                ScheduleRequest(
                    search_id=search_id(),
                    first_run=datetime.now(UTC) + timedelta(days=1),
                    runs=TypeAdapter(int).validate_python(count_input.value),
                    request_id=str(uuid4()),
                )
            )
            return (
                f"Queued {len(result.job_ids)} daily rerun(s) from tomorrow. "
                "Start the managed worker to process them."
            )

        saved_input.on_select = lambda _: attempt(
            lambda: (load(), "Loaded saved screening history.")[1]
        )
        content.controls = [
            ft.Row(
                [
                    saved_input,
                    ft.Button(
                        "Refresh saved searches",
                        on_click=lambda _: attempt(
                            lambda: (load(), "Saved searches refreshed.")[1]
                        ),
                    ),
                ],
                wrap=True,
            ),
            ft.Row([project_input, name_input, query_input], wrap=True),
            ft.Row(
                [
                    year_input,
                    limit_input,
                    ft.Button("Save new search", on_click=lambda _: attempt(save)),
                    ft.Button("Rerun saved query", on_click=lambda _: attempt(rerun)),
                ],
                wrap=True,
            ),
            rows,
            ft.Row([reviewer_input, decision_input, rationale_input], wrap=True),
            ft.Row(
                [
                    ft.Button("Record screening", on_click=lambda _: attempt(review)),
                    tag_input,
                    ft.Button(
                        "Import selected inclusions", on_click=lambda _: attempt(import_selected)
                    ),
                ],
                wrap=True,
            ),
            ft.Row(
                [
                    count_input,
                    ft.Button("Schedule from tomorrow", on_click=lambda _: attempt(schedule)),
                ],
                wrap=True,
            ),
        ]
        load()
        return ft.ExpansionTile(
            title=ft.Text("Saved discovery and screening"),
            controls=[
                ft.Column(
                    [status, content],
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                )
            ],
        )
