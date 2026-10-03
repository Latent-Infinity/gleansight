"""Parameterized, transactional persistence for saved discovery and screening history."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass

from papers.domain.errors import NotFoundError
from papers.domain.screening import DiscoveryRun, Review, SavedSearch, ScreeningDesk
from papers.infra.piccolo.database import PiccoloDatabase


@dataclass(frozen=True, slots=True)
class ScreeningStore:
    database: PiccoloDatabase

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.database.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS saved_searches "
                "(search_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES "
                "projects(project_id), "
                "document_json TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS screening_runs (run_id TEXT PRIMARY KEY, "
                "search_id TEXT NOT NULL REFERENCES saved_searches(search_id), "
                "sequence INTEGER NOT NULL, document_json TEXT NOT NULL, "
                "UNIQUE(search_id, sequence))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS screening_identities (candidate_id TEXT PRIMARY KEY "
                "REFERENCES candidates(candidate_id), doi TEXT UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS screening_aliases (source TEXT NOT NULL, "
                "source_paper_id TEXT NOT NULL, candidate_id TEXT NOT NULL REFERENCES "
                "screening_identities(candidate_id), provenance_json TEXT NOT NULL, "
                "PRIMARY KEY(source, source_paper_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS screening_reviews (review_id TEXT PRIMARY KEY, "
                "search_id TEXT NOT NULL REFERENCES saved_searches(search_id), "
                "candidate_id TEXT NOT NULL "
                "REFERENCES screening_identities(candidate_id), revision INTEGER NOT NULL, "
                "document_json TEXT NOT NULL, UNIQUE(search_id, candidate_id, revision))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS screening_schedules (request_id TEXT PRIMARY KEY, "
                "document_json TEXT NOT NULL)"
            )
            yield connection

    def list(self, project_id: str | None = None) -> tuple[SavedSearch, ...]:
        with self.transaction() as connection:
            return tuple(
                SavedSearch.model_validate_json(row[0])
                for row in connection.execute(
                    "SELECT document_json FROM saved_searches WHERE (? IS NULL OR project_id = ?) "
                    "ORDER BY rowid",
                    (project_id, project_id),
                )
            )

    def get(self, search_id: str) -> ScreeningDesk:
        with self.transaction() as connection:
            return self.read(connection, search_id)

    def read(self, connection: sqlite3.Connection, search_id: str) -> ScreeningDesk:
        row = connection.execute(
            "SELECT document_json FROM saved_searches WHERE search_id = ?", (search_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Saved search not found: {search_id}")
        return ScreeningDesk(
            search=SavedSearch.model_validate_json(row[0]),
            runs=tuple(
                DiscoveryRun.model_validate_json(item[0])
                for item in connection.execute(
                    "SELECT document_json FROM screening_runs WHERE search_id = ? "
                    "ORDER BY sequence",
                    (search_id,),
                )
            ),
            reviews=tuple(
                Review.model_validate_json(item[0])
                for item in connection.execute(
                    "SELECT document_json FROM screening_reviews WHERE search_id "
                    "= ? ORDER BY rowid",
                    (search_id,),
                )
            ),
        )
