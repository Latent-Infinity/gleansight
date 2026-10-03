from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from papers.domain.errors import NotFoundError
from papers.domain.idea_reviews import IdeaReview, IdeaReviewError, ReviewInput, ReviewSelection
from papers.infra.piccolo.database import PiccoloDatabase


def _schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS idea_reviews (review_id TEXT PRIMARY KEY, "
        "bundle_path TEXT NOT NULL, idea_id TEXT NOT NULL, revision INTEGER NOT NULL, "
        "document_json TEXT NOT NULL, UNIQUE(bundle_path, idea_id, revision))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS idea_review_selections "
        "(selection_id TEXT PRIMARY KEY, review_id TEXT NOT NULL, document_json TEXT NOT NULL)"
    )
    for table in ("idea_reviews", "idea_review_selections"):
        for action in ("UPDATE", "DELETE"):
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()}_immutable "
                f"BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable review history'); END"
            )


@dataclass(frozen=True, slots=True)
class IdeaReviewStore:
    database: PiccoloDatabase

    def _rows(self, table: Literal["idea_reviews", "idea_review_selections"]) -> tuple[str, ...]:
        if not self.database.path.is_file():
            return ()
        with closing(
            sqlite3.connect(self.database.path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                is None
            ):
                return ()
            # Table names originate only from this module's two fixed call sites.
            return tuple(
                row[0]
                for row in connection.execute(f"SELECT document_json FROM {table} ORDER BY rowid")
            )

    def history(
        self, bundle: Path | None = None, project_id: str | None = None
    ) -> tuple[IdeaReview, ...]:
        reviews = tuple(IdeaReview.model_validate_json(raw) for raw in self._rows("idea_reviews"))
        return tuple(
            review
            for review in reviews
            if (bundle is None or review.binding.bundle_path == bundle)
            and (project_id is None or review.binding.project_id == project_id)
        )

    def get(self, review_id: str) -> IdeaReview:
        for review in self.history():
            if review.review_id == review_id:
                return review
        raise NotFoundError(f"Idea review not found: {review_id}")

    def selections(self) -> tuple[ReviewSelection, ...]:
        return tuple(
            ReviewSelection.model_validate_json(raw) for raw in self._rows("idea_review_selections")
        )

    def append(self, request: ReviewInput) -> IdeaReview:
        self.database.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            _schema(connection)
            row = connection.execute(
                "SELECT review_id, revision FROM idea_reviews "
                "WHERE bundle_path=? AND idea_id=? ORDER BY revision DESC LIMIT 1",
                (str(request.binding.bundle_path), request.binding.idea_id),
            ).fetchone()
            if (row[0] if row else None) != request.previous_review_id:
                raise IdeaReviewError("Review revision changed; reload before recording a decision")
            review = IdeaReview(
                binding=request.binding,
                reviewer=request.reviewer,
                verdict=request.verdict,
                rationale=request.rationale,
                previous_review_id=request.previous_review_id,
                review_id=uuid4().hex,
                revision=row[1] + 1 if row else 1,
                created_at=datetime.now(UTC).isoformat(),
            )
            connection.execute(
                "INSERT INTO idea_reviews VALUES (?, ?, ?, ?, ?)",
                (
                    review.review_id,
                    str(review.binding.bundle_path),
                    review.binding.idea_id,
                    review.revision,
                    review.model_dump_json(),
                ),
            )
        return review

    def select(self, selection: ReviewSelection) -> None:
        with closing(sqlite3.connect(self.database.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            _schema(connection)
            row = connection.execute(
                "SELECT review_id FROM idea_reviews "
                "WHERE bundle_path=? AND idea_id=? ORDER BY revision DESC LIMIT 1",
                (str(selection.binding.bundle_path), selection.binding.idea_id),
            ).fetchone()
            if row is None or row[0] != selection.review_id:
                raise IdeaReviewError(
                    "Review changed during planning; generated plan is unselected"
                )
            connection.execute(
                "INSERT INTO idea_review_selections VALUES (?, ?, ?)",
                (selection.selection_id, selection.review_id, selection.model_dump_json()),
            )
