from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from piccolo.engine.sqlite import SQLiteEngine, TransactionType
from piccolo.querystring import QueryString

from papers.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from papers.infra.piccolo.database import PiccoloDatabase


def _run_sync[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion. Unlike Piccolo's run_sync, do not retry
    an already-awaited coroutine when the coroutine itself raised RuntimeError.
    """
    try:
        return asyncio.run(coroutine)
    except RuntimeError as exc:
        message = str(exc).lower()
        if "running event loop" not in message:
            raise
        with ThreadPoolExecutor(max_workers=1) as executor:
            return cast(T, executor.submit(asyncio.run, coroutine).result())


MIGRATION_001 = "001_baseline"
MIGRATION_002 = "002_job_integrity_check"
MIGRATION_003 = "003_nsqd_tables"
MIGRATION_004 = "004_nsqd_snapshot_versions"
KNOWN_MIGRATIONS = frozenset({MIGRATION_001, MIGRATION_002, MIGRATION_003, MIGRATION_004})

NSQD_SNAPSHOT_VERSIONED_DDL = """
CREATE TABLE new_nsqd_corpus_snapshots (
    snapshot_id VARCHAR PRIMARY KEY NOT NULL,
    schema_version INTEGER NOT NULL,
    record_ids_json TEXT NOT NULL,
    corpus_version INTEGER UNIQUE NOT NULL
)
"""

EXPECTED_JOB_INDEXES = frozenset(
    {
        "sqlite_autoindex_jobs_1",
        "idx_jobs_unique_active_stage",
        "idx_jobs_unique_analyze",
    }
)

JOB_CHECK_PREDICATE = """
(
  (type = 'discover') OR
  (type IN ('download','convert','embed') AND paper_id IS NOT NULL) OR
  (type = 'analyze' AND paper_id IS NOT NULL AND run_id IS NOT NULL)
)
"""

JOB_INDEX_DDL = (
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_active_stage
    ON jobs(type, paper_id)
    WHERE status IN ('queued','running') AND type IN ('download','convert','embed');
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_analyze
    ON jobs(run_id)
    WHERE type = 'analyze';
    """,
)

_JOB_COPY_COLUMNS = (
    "job_id, type, status, paper_id, run_id, payload_json, "
    "attempts, max_attempts, run_after, last_error, created_at, updated_at"
)


def apply_forward_migrations(database: PiccoloDatabase) -> None:
    _ensure_migrations_table(database)
    _validate_applied_versions(database)
    _apply_001(database)
    _apply_002(database)
    _apply_003(database)
    _apply_004(database)


def _ensure_migrations_table(database: PiccoloDatabase) -> None:
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def _applied_versions(database: PiccoloDatabase) -> set[str]:
    rows = database.fetchall("SELECT version FROM schema_migrations")
    return {str(row["version"]) for row in rows}


def _validate_applied_versions(database: PiccoloDatabase) -> None:
    unknown = _applied_versions(database) - KNOWN_MIGRATIONS
    if unknown:
        versions = ", ".join(sorted(unknown))
        raise ConfigurationError(f"unknown schema migrations: {versions}")


def _record(database: PiccoloDatabase, version: str) -> None:
    database.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        [version, datetime.now(UTC).isoformat()],
    )


def _apply_001(database: PiccoloDatabase) -> None:
    if MIGRATION_001 in _applied_versions(database):
        return
    _record(database, MIGRATION_001)


def _apply_002(database: PiccoloDatabase) -> None:
    if MIGRATION_002 in _applied_versions(database):
        return
    invalid = database.fetchall(
        f"SELECT job_id FROM jobs WHERE NOT {JOB_CHECK_PREDICATE} ORDER BY job_id"
    )
    if invalid:
        ids = ", ".join(str(row["job_id"]) for row in invalid)
        raise ConfigurationError(f"jobs rows fail integrity check: {ids}")
    unexpected = _unexpected_job_objects(database)
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise ConfigurationError(f"unexpected jobs schema objects: {names}")
    engine = database.engine
    new_jobs_ddl = _new_jobs_ddl(database)

    async def rebuild() -> None:
        async with engine.transaction(transaction_type=TransactionType.immediate):
            await engine.run_querystring(QueryString(new_jobs_ddl))
            await copy_jobs_into_new_table(engine)
            await engine.run_querystring(QueryString("DROP TABLE jobs"))
            await engine.run_querystring(QueryString("ALTER TABLE new_jobs RENAME TO jobs"))
            for statement in JOB_INDEX_DDL:
                await engine.run_ddl(statement)
            await engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_002,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(rebuild())


def _apply_003(database: PiccoloDatabase) -> None:
    if MIGRATION_003 in _applied_versions(database):
        return
    from nsqd.infra.piccolo.schema import (
        NSQD_TABLE_DDL,
        NSQD_TABLE_DDL_BY_NAME,
        normalize_create_table_sql,
    )

    existing_rows = database.fetchall(
        """
        SELECT name, sql FROM sqlite_schema
        WHERE type = 'table' AND name IN (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "nsqd_jobs",
            "nsqd_corpus_records",
            "nsqd_corpus_snapshots",
            "nsqd_candidates",
            "nsqd_frontier_cards",
            "nsqd_elites",
            "nsqd_morphospace",
        ],
    )
    expected_sql = {
        name: normalize_create_table_sql(statement)
        for name, statement in NSQD_TABLE_DDL_BY_NAME.items()
    }
    for row in existing_rows:
        name = str(row["name"])
        sql = row["sql"]
        if not isinstance(sql, str) or normalize_create_table_sql(sql) != expected_sql[name]:
            raise ConfigurationError(f"existing NSQD table schema mismatch: {name}")

    async def create_nsqd_tables() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            for statement in NSQD_TABLE_DDL:
                await database.engine.run_querystring(QueryString(statement))
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_003,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(create_nsqd_tables())


def _apply_004(database: PiccoloDatabase) -> None:
    if MIGRATION_004 in _applied_versions(database):
        _validate_snapshot_version_schema(database)
        return

    columns = {
        str(row["name"]) for row in database.fetchall("PRAGMA table_info(nsqd_corpus_snapshots)")
    }
    if "corpus_version" in columns:
        _validate_snapshot_version_schema(database)
        _record(database, MIGRATION_004)
        return

    async def rebuild_snapshots() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            await database.engine.run_querystring(QueryString(NSQD_SNAPSHOT_VERSIONED_DDL))
            await database.engine.run_querystring(
                QueryString(
                    """
                    INSERT INTO new_nsqd_corpus_snapshots (
                        snapshot_id, schema_version, record_ids_json, corpus_version
                    )
                    SELECT snapshot_id, schema_version, record_ids_json,
                           ROW_NUMBER() OVER (ORDER BY rowid)
                    FROM nsqd_corpus_snapshots
                    """
                )
            )
            await database.engine.run_querystring(QueryString("DROP TABLE nsqd_corpus_snapshots"))
            await database.engine.run_querystring(
                QueryString("ALTER TABLE new_nsqd_corpus_snapshots RENAME TO nsqd_corpus_snapshots")
            )
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_004,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(rebuild_snapshots())
    _validate_snapshot_version_schema(database)


def _validate_snapshot_version_schema(database: PiccoloDatabase) -> None:
    rows = database.fetchall("PRAGMA table_info(nsqd_corpus_snapshots)")
    columns = {str(row["name"]): row for row in rows}
    expected = {"snapshot_id", "schema_version", "record_ids_json", "corpus_version"}
    if set(columns) != expected or int(columns["corpus_version"]["notnull"]) != 1:
        raise ConfigurationError("existing NSQD snapshot version schema mismatch")

    unique_version = False
    for index in database.fetchall("PRAGMA index_list(nsqd_corpus_snapshots)"):
        if int(index["unique"]) != 1:
            continue
        name = str(index["name"])
        indexed = database.fetchall(f"PRAGMA index_info({name})")
        if [str(row["name"]) for row in indexed] == ["corpus_version"]:
            unique_version = True
            break
    if not unique_version:
        raise ConfigurationError("existing NSQD snapshot version schema mismatch")


def _new_jobs_ddl(database: PiccoloDatabase) -> str:
    row = database.fetchone("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'jobs'")
    if row is None or not isinstance(row["sql"], str):
        raise ConfigurationError("jobs table schema is unavailable")
    original = row["sql"]
    prefix = 'CREATE TABLE "jobs"'
    if not original.startswith(prefix) or not original.endswith(")"):
        raise ConfigurationError("jobs table schema has an unexpected form")
    rebuilt = original.replace(prefix, 'CREATE TABLE "new_jobs"', 1)
    return f"{rebuilt[:-1]}, CHECK {JOB_CHECK_PREDICATE})"


def _unexpected_job_objects(database: PiccoloDatabase) -> set[str]:
    rows = database.fetchall(
        """
        SELECT type, name FROM sqlite_schema
        WHERE type IN ('index', 'trigger')
          AND tbl_name = 'jobs'
        """
    )
    found = {str(row["name"]) for row in rows}
    return found - EXPECTED_JOB_INDEXES


async def copy_jobs_into_new_table(engine: SQLiteEngine) -> None:
    await engine.run_querystring(
        QueryString(
            f"INSERT INTO new_jobs ({_JOB_COPY_COLUMNS}) SELECT {_JOB_COPY_COLUMNS} FROM jobs"
        )
    )
