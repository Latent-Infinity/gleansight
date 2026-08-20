from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from papers.domain.errors import ConfigurationError
from papers.infra.piccolo.database import _TABLES, PiccoloDatabase

_NOW = datetime.now(UTC).isoformat()
_JOB_COLUMNS = (
    "job_id, type, status, paper_id, run_id, payload_json, "
    "attempts, max_attempts, run_after, last_error, created_at, updated_at"
)


def _build_previous_baseline(path: Path) -> PiccoloDatabase:
    db = PiccoloDatabase(path)
    for table in _TABLES:
        table.create_table(if_not_exists=True).run_sync()
    db._create_indexes_and_fts()
    return db


def _insert_job(
    db: PiccoloDatabase,
    *,
    job_id: str,
    type: str,
    paper_id: str | None,
    run_id: str | None,
    payload: str = "{}",
) -> None:
    db.execute(
        f"""
        INSERT INTO jobs ({_JOB_COLUMNS})
        VALUES (?, ?, 'queued', ?, ?, ?, 0, 3, NULL, NULL, ?, ?)
        """,
        [job_id, type, paper_id, run_id, payload, _NOW, _NOW],
    )


def _jobs_sql(db: PiccoloDatabase) -> str:
    row = db.fetchone("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'jobs'")
    assert row is not None
    return str(row["sql"])


def _index_names(db: PiccoloDatabase) -> set[str]:
    rows = db.fetchall("SELECT name FROM sqlite_schema WHERE tbl_name = 'jobs' AND type = 'index'")
    return {row["name"] for row in rows}


def test_previous_baseline_allows_download_without_paper_id(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "old.sqlite")
    _insert_job(db, job_id="dl-null", type="download", paper_id=None, run_id=None)
    row = db.fetchone("SELECT job_id FROM jobs WHERE job_id = ?", ["dl-null"])
    assert row is not None


def test_forward_upgrade_adds_check_and_preserves_rows_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    db = _build_previous_baseline(path)
    _insert_job(
        db,
        job_id="dl-ok",
        type="download",
        paper_id="paper-1",
        run_id=None,
        payload='{"url":"https://example.test/a.pdf"}',
    )
    _insert_job(
        db,
        job_id="an-ok",
        type="analyze",
        paper_id="paper-1",
        run_id="run-1",
        payload='{"prompt":"v1"}',
    )

    db.initialize_schema()

    sql = _jobs_sql(db)
    assert "CHECK" in sql.upper()
    assert "download" in sql
    names = _index_names(db)
    assert "idx_jobs_unique_active_stage" in names
    assert "idx_jobs_unique_analyze" in names

    rows = {
        row["job_id"]: row
        for row in db.fetchall(f"SELECT {_JOB_COLUMNS} FROM jobs ORDER BY job_id")
    }
    assert set(rows) == {"an-ok", "dl-ok"}
    assert rows["dl-ok"]["paper_id"] == "paper-1"
    assert rows["dl-ok"]["payload_json"] == '{"url":"https://example.test/a.pdf"}'
    assert rows["an-ok"]["run_id"] == "run-1"
    assert rows["an-ok"]["payload_json"] == '{"prompt":"v1"}'

    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert "001_baseline" in versions
    assert "002_job_integrity_check" in versions

    _insert_job(db, job_id="disc-1", type="discover", paper_id=None, run_id=None)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(db, job_id="dl-bad", type="download", paper_id=None, run_id=None)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(db, job_id="an-bad", type="analyze", paper_id="paper-1", run_id=None)


def test_forward_upgrade_preserves_column_defaults(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "defaults.sqlite")
    before = {row["name"]: row["dflt_value"] for row in db.fetchall("PRAGMA table_info(jobs)")}

    db.initialize_schema()

    after = {row["name"]: row["dflt_value"] for row in db.fetchall("PRAGMA table_info(jobs)")}
    assert after == before


def test_unknown_future_migration_rejects_older_runner(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "future.sqlite")
    db.execute(
        """
        CREATE TABLE schema_migrations (
            version VARCHAR(255) PRIMARY KEY NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    db.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        ["999_future", _NOW],
    )

    with pytest.raises(ConfigurationError, match="unknown schema migrations: 999_future"):
        db.initialize_schema()

    assert "CHECK" not in _jobs_sql(db).upper()


def test_fresh_database_applies_baseline_and_check(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "fresh.sqlite")
    db.initialize_schema()
    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert versions == {"001_baseline", "002_job_integrity_check", "003_nsqd_tables"}
    assert "CHECK" in _jobs_sql(db).upper()
    db.initialize_schema()
    again = db.fetchall("SELECT version FROM schema_migrations")
    assert len(again) == 3


def test_nsqd_migration_is_atomic_when_ddl_fails(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "nsqd-atomic.sqlite")
    with (
        patch(
            "nsqd.infra.piccolo.schema.NSQD_TABLE_DDL",
            (
                "CREATE TABLE nsqd_jobs (job_id VARCHAR PRIMARY KEY NOT NULL)",
                "CREATE TABLE nsqd_jobs (job_id VARCHAR PRIMARY KEY NOT NULL)",
            ),
        ),
        pytest.raises(sqlite3.OperationalError),
    ):
        db.initialize_schema()

    assert (
        db.fetchone("SELECT name FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_jobs'")
        is None
    )
    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = '003_nsqd_tables'")
        is None
    )


def test_nsqd_migration_recovers_when_tables_exist_without_ledger_row(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "nsqd-recover.sqlite")
    db.execute(
        """
        CREATE TABLE nsqd_jobs (
            job_id VARCHAR PRIMARY KEY NOT NULL,
            type VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            payload_json TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            run_after TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CHECK (type IN ('harvest','project','diverge','ground','score','rescore')),
            CHECK (status IN ('queued','running','succeeded','failed','canceled'))
        )
        """
    )
    db.execute(
        """
        CREATE TABLE nsqd_corpus_records (
            record_id VARCHAR PRIMARY KEY NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )

    db.initialize_schema()

    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert "003_nsqd_tables" in versions
    names = {
        str(row["name"])
        for row in db.fetchall("SELECT name FROM sqlite_schema WHERE type = 'table'")
    }
    assert {
        "nsqd_jobs",
        "nsqd_corpus_records",
        "nsqd_corpus_snapshots",
        "nsqd_candidates",
        "nsqd_frontier_cards",
        "nsqd_elites",
        "nsqd_morphospace",
    } <= names


def test_nsqd_migration_rejects_malformed_existing_nsqd_table(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "nsqd-malformed.sqlite")
    db.execute(
        """
        CREATE TABLE nsqd_jobs (
            job_id VARCHAR PRIMARY KEY NOT NULL,
            type VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            payload_json TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            run_after TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    with pytest.raises(ConfigurationError, match="nsqd_jobs"):
        db.initialize_schema()

    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = '003_nsqd_tables'")
        is None
    )


def test_invalid_existing_row_aborts_and_leaves_old_table(tmp_path: Path) -> None:
    path = tmp_path / "bad.sqlite"
    db = _build_previous_baseline(path)
    _insert_job(db, job_id="dl-bad", type="download", paper_id=None, run_id=None)
    _insert_job(db, job_id="dl-ok", type="download", paper_id="paper-1", run_id=None)

    with pytest.raises(ConfigurationError, match="dl-bad"):
        db.initialize_schema()

    sql = _jobs_sql(db)
    assert "CHECK" not in sql.upper()
    ids = {row["job_id"] for row in db.fetchall("SELECT job_id FROM jobs")}
    assert ids == {"dl-bad", "dl-ok"}
    assert db.fetchone(
        "SELECT name FROM sqlite_schema WHERE name = 'schema_migrations'"
    ) is None or (
        db.fetchone(
            "SELECT version FROM schema_migrations WHERE version = '002_job_integrity_check'"
        )
        is None
    )


def test_mid_rebuild_abort_leaves_original_jobs_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "abort.sqlite"
    db = _build_previous_baseline(path)
    _insert_job(db, job_id="dl-ok", type="download", paper_id="paper-1", run_id=None)
    original_sql = _jobs_sql(db)

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("copy aborted")

    with (
        patch(
            "papers.infra.piccolo.migrations.runner.copy_jobs_into_new_table",
            new=boom,
        ),
        pytest.raises(RuntimeError, match="copy aborted"),
    ):
        db.initialize_schema()

    assert _jobs_sql(db) == original_sql
    names = _index_names(db)
    assert "idx_jobs_unique_active_stage" in names
    assert "idx_jobs_unique_analyze" in names
    row = db.fetchone("SELECT job_id FROM jobs WHERE job_id = ?", ["dl-ok"])
    assert row is not None


def test_unexpected_jobs_index_rejects_migration(tmp_path: Path) -> None:
    path = tmp_path / "extra.sqlite"
    db = _build_previous_baseline(path)
    db.execute("CREATE INDEX idx_jobs_unexpected ON jobs(status)")
    with pytest.raises(ConfigurationError, match="idx_jobs_unexpected"):
        db.initialize_schema()
    names = _index_names(db)
    assert "idx_jobs_unexpected" in names
    assert "CHECK" not in _jobs_sql(db).upper()
