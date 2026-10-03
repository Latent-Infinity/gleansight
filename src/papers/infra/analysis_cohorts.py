"""Immutable cohort selections stored in the explicitly supplied workspace database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass

from papers.domain.analysis_comparison import SavedCohort
from papers.domain.errors import NotFoundError
from papers.infra.piccolo.database import PiccoloDatabase


@dataclass(frozen=True, slots=True)
class AnalysisCohortStore:
    database: PiccoloDatabase

    def save(self, cohort: SavedCohort) -> None:
        """Create the table on first write and insert without upsert or replacement."""
        with closing(sqlite3.connect(self.database.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS analysis_evaluation_cohorts "
                "(cohort_id TEXT PRIMARY KEY, document_json TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO analysis_evaluation_cohorts VALUES (?, ?)",
                (cohort.cohort_id, cohort.model_dump_json()),
            )

    def get(self, cohort_id: str) -> SavedCohort:
        exists = self.database.fetchone(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'analysis_evaluation_cohorts'"
        )
        row = (
            None
            if exists is None
            else self.database.fetchone(
                "SELECT document_json FROM analysis_evaluation_cohorts WHERE cohort_id = ?",
                [cohort_id],
            )
        )
        if row is None:
            message = f"Evaluation cohort not found: {cohort_id}"
            raise NotFoundError(message)
        return SavedCohort.model_validate_json(row["document_json"])

    def list(self) -> tuple[SavedCohort, ...]:
        """Read at most 100 saved selections without creating storage on a read."""
        exists = self.database.fetchone(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'analysis_evaluation_cohorts'"
        )
        if exists is None:
            return ()
        rows = self.database.fetchall(
            "SELECT document_json FROM analysis_evaluation_cohorts ORDER BY rowid DESC LIMIT 100"
        )
        return tuple(SavedCohort.model_validate_json(row["document_json"]) for row in rows)
