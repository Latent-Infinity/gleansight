"""Readable candidate provenance and review history for the saved-search queue."""

import flet as ft

from papers.domain.screening import Observation, Review


def screening_row(
    item: Observation, sequence: int, history: tuple[Review, ...], selected: set[str]
) -> ft.Control:
    checkbox = ft.Checkbox(
        label=f"Run {sequence} · {item.delta.replace('_', ' ').title()} · {item.metadata.title}"
    )

    def select(event: ft.Event[ft.Checkbox]) -> None:
        if event.control.value:
            selected.add(item.candidate_id)
        else:
            selected.discard(item.candidate_id)

    checkbox.on_change = select
    return ft.Column(
        [
            checkbox,
            ft.Text(
                f"{item.metadata.year or 'Year missing'} · DOI: {item.doi or 'missing'} · "
                f"{item.source}: {item.source_paper_id}",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Text(
                f"Current decision: {history[-1].decision.title()}" if history else "Not screened",
                size=12,
            ),
            ft.ExpansionTile(
                title=ft.Text("Abstract, authors and review history", size=12),
                controls=[
                    ft.Text(", ".join(item.metadata.authors) or "Authors missing", size=12),
                    ft.Text(item.metadata.abstract or "Abstract missing", size=12),
                    *[
                        ft.Text(
                            f"Revision {review.revision} · {review.decision.title()} · "
                            f"{review.reviewer}: {review.rationale}",
                            size=12,
                        )
                        for review in history
                    ],
                ],
            ),
        ],
        spacing=2,
    )
