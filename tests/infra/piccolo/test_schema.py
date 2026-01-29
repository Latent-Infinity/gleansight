from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.infra.piccolo.database import PiccoloDatabase


def test_schema_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    db = PiccoloDatabase(db_path)
    db.initialize_schema()

    rows = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
    )
    names = {row["name"] for row in rows}

    assert "papers" in names
    assert "jobs" in names
    assert "analysis_runs" in names
    assert "analysis_extractions" in names
    assert "papers_fts" in names
    assert "extractions_fts" in names


def test_schema_enforces_unique_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "unique.sqlite"
    db = PiccoloDatabase(db_path)
    db.initialize_schema()

    now = datetime.now(UTC).isoformat()

    db.execute(
        """
        INSERT INTO candidates (
            candidate_id, source, source_paper_id, title, authors_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ["cand-1", "source", "spid-1", "Title", "[]", now, now],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO candidates (
                candidate_id, source, source_paper_id, title, authors_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ["cand-2", "source", "spid-1", "Title 2", "[]", now, now],
        )

    db.execute(
        """
        INSERT INTO prompt_versions (
            prompt_version_id, prompt_id, version, body, output_format, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ["pv-1", "prompt-1", 1, "body", "json_only", now],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO prompt_versions (
                prompt_version_id, prompt_id, version, body, output_format, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["pv-2", "prompt-1", 1, "body2", "json_only", now],
        )

    db.execute(
        """
        INSERT INTO jobs (
            job_id, type, status, paper_id, run_id, payload_json, attempts, max_attempts,
            run_after, last_error, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "job-1",
            "download",
            "queued",
            "paper-1",
            None,
            "{}",
            0,
            3,
            None,
            None,
            now,
            now,
        ],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO jobs (
                job_id, type, status, paper_id, run_id, payload_json, attempts, max_attempts,
                run_after, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "job-2",
                "download",
                "queued",
                "paper-1",
                None,
                "{}",
                0,
                3,
                None,
                None,
                now,
                now,
            ],
        )

    db.execute(
        """
        INSERT INTO paper_external_ids (
            paper_external_id_id, paper_id, kind, value, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ["ext-1", "paper-1", "doi", "10.1234/abc", now],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO paper_external_ids (
                paper_external_id_id, paper_id, kind, value, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ["ext-2", "paper-2", "doi", "10.1234/abc", now],
        )

    db.execute(
        """
        INSERT INTO paper_projects (
            paper_id, project_id, label, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        ["paper-1", "project-1", None, now],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO paper_projects (
                paper_id, project_id, label, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            ["paper-1", "project-1", "duplicate", now],
        )

    db.execute(
        """
        INSERT INTO paper_tags (
            paper_id, tag_id, confidence, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        ["paper-1", "tag-1", 0.9, now],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO paper_tags (
                paper_id, tag_id, confidence, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            ["paper-1", "tag-1", 0.5, now],
        )
