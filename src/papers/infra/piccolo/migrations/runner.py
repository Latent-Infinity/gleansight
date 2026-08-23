from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from piccolo.engine.sqlite import SQLiteEngine, TransactionType
from piccolo.querystring import QueryString

from nsqd.domain.policy import FINANCE_POLICY, archive_cell_key, get_policy
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
MIGRATION_005 = "005_nsqd_policy_verdicts"
MIGRATION_006 = "006_nsqd_legacy_finance_policy_backfill"
MIGRATION_007 = "007_nsqd_map_job_type"
MIGRATION_008 = "008_nsqd_acquisition_cycles"
MIGRATION_009 = "009_nsqd_acquire_job_type"
KNOWN_MIGRATIONS = frozenset(
    {
        MIGRATION_001,
        MIGRATION_002,
        MIGRATION_003,
        MIGRATION_004,
        MIGRATION_005,
        MIGRATION_006,
        MIGRATION_007,
        MIGRATION_008,
        MIGRATION_009,
    }
)

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
    _apply_005(database)
    _apply_006(database)
    _apply_007(database)
    _apply_008(database)
    _apply_009(database)


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
        if name == "nsqd_jobs" and isinstance(sql, str):
            if _classify_nsqd_jobs_sql(sql) in {"legacy", "map_era", "current"}:
                continue
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


def _apply_005(database: PiccoloDatabase) -> None:
    if MIGRATION_005 in _applied_versions(database):
        _validate_policy_verdict_schema(database)
        return

    if (
        database.fetchone(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_policy_verdicts'"
        )
        is not None
    ):
        _validate_policy_verdict_schema(database)
        _record(database, MIGRATION_005)
        return

    async def create_policy_verdicts() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            await database.engine.run_querystring(
                QueryString(
                    """
                    CREATE TABLE IF NOT EXISTS nsqd_policy_verdicts (
                        snapshot_id VARCHAR NOT NULL,
                        domain_policy_id VARCHAR NOT NULL,
                        verdict TEXT NOT NULL,
                        PRIMARY KEY (snapshot_id, domain_policy_id)
                    )
                    """
                )
            )
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_005,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(create_policy_verdicts())
    _validate_policy_verdict_schema(database)


def _apply_006(database: PiccoloDatabase) -> None:
    if MIGRATION_006 in _applied_versions(database):
        _validate_policy_backfill_state(database)
        return

    async def migrate_legacy_policy_state() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            record_rows = await database.engine.run_querystring(
                QueryString(
                    "SELECT record_id, payload_json FROM nsqd_corpus_records ORDER BY record_id"
                )
            )
            candidate_rows = await database.engine.run_querystring(
                QueryString(
                    "SELECT artifact_hash, payload_json FROM nsqd_candidates ORDER BY artifact_hash"
                )
            )
            card_rows = await database.engine.run_querystring(
                QueryString(
                    "SELECT card_id, cell_id, payload_json "
                    "FROM nsqd_frontier_cards ORDER BY card_id"
                )
            )
            elite_rows = await database.engine.run_querystring(
                QueryString("SELECT cell_id, card_id FROM nsqd_elites ORDER BY cell_id")
            )

            record_updates = _plan_record_policy_updates(record_rows, strict=False)
            candidate_updates = _plan_candidate_policy_updates(candidate_rows, strict=False)
            card_updates = _plan_card_policy_updates(card_rows, strict=False)
            elite_updates, elite_deletes = _plan_elite_key_updates(elite_rows, strict=False)

            for record_id, payload_json in record_updates:
                await database.engine.run_querystring(
                    QueryString(
                        "UPDATE nsqd_corpus_records SET payload_json = {} WHERE record_id = {}",
                        payload_json,
                        record_id,
                    )
                )
            for artifact_hash, payload_json in candidate_updates:
                await database.engine.run_querystring(
                    QueryString(
                        "UPDATE nsqd_candidates SET payload_json = {} WHERE artifact_hash = {}",
                        payload_json,
                        artifact_hash,
                    )
                )
            for card_id, cell_id, payload_json in card_updates:
                await database.engine.run_querystring(
                    QueryString(
                        """
                        UPDATE nsqd_frontier_cards
                        SET cell_id = {}, payload_json = {}
                        WHERE card_id = {}
                        """,
                        cell_id,
                        payload_json,
                        card_id,
                    )
                )
            for cell_id in elite_deletes:
                await database.engine.run_querystring(
                    QueryString("DELETE FROM nsqd_elites WHERE cell_id = {}", cell_id)
                )
            for old_cell_id, new_cell_id, card_id in elite_updates:
                await database.engine.run_querystring(
                    QueryString(
                        "UPDATE nsqd_elites SET cell_id = {} WHERE cell_id = {} AND card_id = {}",
                        new_cell_id,
                        old_cell_id,
                        card_id,
                    )
                )
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_006,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(migrate_legacy_policy_state())
    _validate_policy_backfill_state(database)


def _apply_007(database: PiccoloDatabase) -> None:
    observed_schema = _nsqd_jobs_schema_state(database)
    if MIGRATION_007 in _applied_versions(database):
        if observed_schema not in {"map_era", "current"}:
            raise ConfigurationError("existing nsqd_jobs schema mismatch")
        return

    if observed_schema in {"map_era", "current"}:
        _record(database, MIGRATION_007)
        return
    if observed_schema != "legacy":
        raise ConfigurationError("existing nsqd_jobs schema mismatch")

    async def rebuild_nsqd_jobs() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            await database.engine.run_querystring(
                QueryString(_new_nsqd_jobs_ddl(_map_era_nsqd_jobs_ddl()))
            )
            await copy_nsqd_jobs_into_new_table(database.engine)
            await database.engine.run_querystring(QueryString("DROP TABLE nsqd_jobs"))
            await database.engine.run_querystring(
                QueryString("ALTER TABLE new_nsqd_jobs RENAME TO nsqd_jobs")
            )
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_007,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(rebuild_nsqd_jobs())
    if _nsqd_jobs_schema_state(database) != "map_era":
        raise ConfigurationError("existing nsqd_jobs schema mismatch")


def _apply_008(database: PiccoloDatabase) -> None:
    if MIGRATION_008 in _applied_versions(database):
        _validate_acquisition_cycle_schema(database)
        return

    if (
        database.fetchone(
            "SELECT name FROM sqlite_schema WHERE type = 'table' "
            "AND name = 'nsqd_acquisition_cycles'"
        )
        is not None
    ):
        _validate_acquisition_cycle_schema(database)
        _record(database, MIGRATION_008)
        return

    async def create_acquisition_cycles() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            await database.engine.run_querystring(
                QueryString(
                    """
                    CREATE TABLE IF NOT EXISTS nsqd_acquisition_cycles (
                        cycle_id VARCHAR PRIMARY KEY NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )
            )
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_008,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(create_acquisition_cycles())
    _validate_acquisition_cycle_schema(database)


def _apply_009(database: PiccoloDatabase) -> None:
    observed_schema = _nsqd_jobs_schema_state(database)
    if MIGRATION_009 in _applied_versions(database):
        if observed_schema != "current":
            raise ConfigurationError("existing nsqd_jobs schema mismatch")
        return

    if observed_schema == "current":
        _record(database, MIGRATION_009)
        return
    if observed_schema != "map_era":
        raise ConfigurationError("existing nsqd_jobs schema mismatch")

    async def rebuild_nsqd_jobs() -> None:
        async with database.engine.transaction(transaction_type=TransactionType.immediate):
            await database.engine.run_querystring(
                QueryString(_new_nsqd_jobs_ddl(_current_nsqd_jobs_ddl()))
            )
            await copy_nsqd_jobs_into_new_table(database.engine)
            await database.engine.run_querystring(QueryString("DROP TABLE nsqd_jobs"))
            await database.engine.run_querystring(
                QueryString("ALTER TABLE new_nsqd_jobs RENAME TO nsqd_jobs")
            )
            await database.engine.run_querystring(
                QueryString(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ({}, {})",
                    MIGRATION_009,
                    datetime.now(UTC).isoformat(),
                )
            )

    _run_sync(rebuild_nsqd_jobs())
    if _nsqd_jobs_schema_state(database) != "current":
        raise ConfigurationError("existing nsqd_jobs schema mismatch")


def _validate_acquisition_cycle_schema(database: PiccoloDatabase) -> None:
    rows = database.fetchall("PRAGMA table_info(nsqd_acquisition_cycles)")
    expected = [
        ("cycle_id", "VARCHAR", 1, 1),
        ("payload_json", "TEXT", 1, 0),
    ]
    observed = [
        (str(row["name"]), str(row["type"]), int(row["notnull"]), int(row["pk"])) for row in rows
    ]
    if observed != expected:
        raise ConfigurationError("existing NSQD acquisition cycle schema mismatch")


def _validate_policy_verdict_schema(database: PiccoloDatabase) -> None:
    rows = database.fetchall("PRAGMA table_info(nsqd_policy_verdicts)")
    expected = [
        ("snapshot_id", "VARCHAR", 1, 1),
        ("domain_policy_id", "VARCHAR", 1, 2),
        ("verdict", "TEXT", 1, 0),
    ]
    observed = [
        (str(row["name"]), str(row["type"]), int(row["notnull"]), int(row["pk"])) for row in rows
    ]
    if observed != expected:
        raise ConfigurationError("existing NSQD policy verdict schema mismatch")


def _nsqd_jobs_schema_state(database: PiccoloDatabase) -> str:
    row = database.fetchone(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_jobs'"
    )
    if row is None or not isinstance(row["sql"], str):
        raise ConfigurationError("existing nsqd_jobs schema mismatch")
    return _classify_nsqd_jobs_sql(str(row["sql"]))


def _classify_nsqd_jobs_sql(sql: str) -> str:
    from nsqd.infra.piccolo.schema import normalize_create_table_sql

    observed = normalize_create_table_sql(sql.replace('"', ""))
    current = normalize_create_table_sql(_current_nsqd_jobs_ddl())
    if observed == current:
        return "current"
    map_era = normalize_create_table_sql(_map_era_nsqd_jobs_ddl())
    if observed == map_era:
        return "map_era"
    legacy = normalize_create_table_sql(_legacy_nsqd_jobs_ddl())
    if observed == legacy:
        return "legacy"
    return "unexpected"


def _current_nsqd_jobs_ddl() -> str:
    from nsqd.infra.piccolo.schema import NSQD_TABLE_DDL_BY_NAME

    return NSQD_TABLE_DDL_BY_NAME["nsqd_jobs"]


def _map_era_nsqd_jobs_ddl() -> str:
    return _current_nsqd_jobs_ddl().replace(",'acquire'", "")


def _legacy_nsqd_jobs_ddl() -> str:
    return _map_era_nsqd_jobs_ddl().replace(",'map'", "")


def _new_nsqd_jobs_ddl(ddl: str) -> str:
    return ddl.replace("CREATE TABLE IF NOT EXISTS nsqd_jobs", "CREATE TABLE new_nsqd_jobs")


async def copy_nsqd_jobs_into_new_table(engine: SQLiteEngine) -> None:
    await engine.run_querystring(
        QueryString(
            """
            INSERT INTO new_nsqd_jobs (
                job_id, type, status, payload_json, attempts, max_attempts,
                run_after, last_error, created_at, updated_at
            )
            SELECT job_id, type, status, payload_json, attempts, max_attempts,
                   run_after, last_error, created_at, updated_at
            FROM nsqd_jobs
            """
        )
    )


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


def _validate_policy_backfill_state(database: PiccoloDatabase) -> None:
    _plan_record_policy_updates(
        database.fetchall(
            "SELECT record_id, payload_json FROM nsqd_corpus_records ORDER BY record_id"
        ),
        strict=True,
    )
    _plan_candidate_policy_updates(
        database.fetchall(
            "SELECT artifact_hash, payload_json FROM nsqd_candidates ORDER BY artifact_hash"
        ),
        strict=True,
    )
    _plan_card_policy_updates(
        database.fetchall(
            "SELECT card_id, cell_id, payload_json FROM nsqd_frontier_cards ORDER BY card_id"
        ),
        strict=True,
    )
    _plan_elite_key_updates(
        database.fetchall("SELECT cell_id, card_id FROM nsqd_elites ORDER BY cell_id"),
        strict=True,
    )


def _plan_record_policy_updates(
    rows: list[dict[str, Any]],
    *,
    strict: bool,
) -> list[tuple[str, str]]:
    updates: list[tuple[str, str]] = []
    for row in rows:
        record_id = str(row["record_id"])
        payload = _load_json_object(str(row["payload_json"]), label=f"corpus record {record_id}")
        policy_id = payload.get("domain_policy_id")
        changed = False
        if policy_id is None:
            if strict:
                raise ConfigurationError(
                    f"corpus record {record_id} is missing domain_policy_id after migration 006"
                )
            payload["domain_policy_id"] = FINANCE_POLICY.policy_id
            changed = True
        else:
            normalized_policy_id = _normalize_policy_id(
                policy_id, label=f"corpus record {record_id}"
            )
            if normalized_policy_id != policy_id:
                payload["domain_policy_id"] = normalized_policy_id
                changed = True
        if changed:
            updates.append(
                (record_id, _dump_json_object(payload, label=f"corpus record {record_id}"))
            )
    return updates


def _plan_candidate_policy_updates(
    rows: list[dict[str, Any]],
    *,
    strict: bool,
) -> list[tuple[str, str]]:
    updates: list[tuple[str, str]] = []
    for row in rows:
        artifact_hash = str(row["artifact_hash"])
        payload = _load_json_object(
            str(row["payload_json"]), label=f"candidate artifact {artifact_hash}"
        )
        candidate = payload.get("candidate")
        if not isinstance(candidate, dict):
            raise ConfigurationError(
                f"candidate artifact {artifact_hash} candidate must be an object"
            )
        changed = False
        policy_id = candidate.get("domain_policy_id")
        if policy_id is None:
            if strict:
                raise ConfigurationError(
                    "candidate artifact "
                    f"{artifact_hash} is missing candidate.domain_policy_id "
                    "after migration 006"
                )
            _require_candidate_maps_to_policy(
                candidate,
                policy_id=FINANCE_POLICY.policy_id,
                label=f"candidate artifact {artifact_hash}",
            )
            candidate = dict(candidate)
            candidate["domain_policy_id"] = FINANCE_POLICY.policy_id
            payload["candidate"] = candidate
            changed = True
            normalized_policy_id = FINANCE_POLICY.policy_id
        else:
            normalized_policy_id = _normalize_policy_id(
                policy_id, label=f"candidate artifact {artifact_hash}"
            )
            if normalized_policy_id != policy_id:
                candidate = dict(candidate)
                candidate["domain_policy_id"] = normalized_policy_id
                payload["candidate"] = candidate
                changed = True
        _require_candidate_maps_to_policy(
            candidate,
            policy_id=normalized_policy_id,
            label=f"candidate artifact {artifact_hash}",
        )
        if changed:
            updates.append(
                (
                    artifact_hash,
                    _dump_json_object(payload, label=f"candidate artifact {artifact_hash}"),
                )
            )
    return updates


def _plan_card_policy_updates(
    rows: list[dict[str, Any]],
    *,
    strict: bool,
) -> list[tuple[str, str, str]]:
    updates: list[tuple[str, str, str]] = []
    for row in rows:
        card_id = str(row["card_id"])
        stored_cell_id = str(row["cell_id"])
        payload = _load_json_object(str(row["payload_json"]), label=f"frontier card {card_id}")
        payload_card_id = payload.get("card_id")
        if payload_card_id is not None and str(payload_card_id) != card_id:
            raise ConfigurationError(f"frontier card {card_id} payload card_id mismatch")
        payload_cell_id = payload.get("cell_id")
        if not isinstance(payload_cell_id, str) or not payload_cell_id:
            raise ConfigurationError(f"frontier card {card_id} cell_id is required")
        if payload_cell_id != stored_cell_id:
            raise ConfigurationError(f"frontier card {card_id} stored cell_id mismatch")

        normalized_payload, changed = _normalize_card_payload(
            payload, card_id=card_id, strict=strict
        )
        if changed:
            updates.append(
                (
                    card_id,
                    stored_cell_id,
                    _dump_json_object(normalized_payload, label=f"frontier card {card_id}"),
                )
            )
    return updates


def _plan_elite_key_updates(
    rows: list[dict[str, Any]],
    *,
    strict: bool,
) -> tuple[list[tuple[str, str, str]], list[str]]:
    desired_rows: dict[str, tuple[str, str]] = {}
    raw_keys_to_delete: list[str] = []

    for row in rows:
        original_key = str(row["cell_id"])
        card_id = str(row["card_id"])
        normalized_key = _normalize_elite_key(original_key, strict=strict)
        existing = desired_rows.get(normalized_key)
        if existing is None:
            desired_rows[normalized_key] = (original_key, card_id)
            continue
        existing_original_key, existing_card_id = existing
        if existing_card_id != card_id:
            raise ConfigurationError(
                f"conflicting scoped elite for {normalized_key}: {existing_card_id} vs {card_id}"
            )
        if original_key == normalized_key:
            raw_keys_to_delete.append(existing_original_key)
            desired_rows[normalized_key] = (original_key, card_id)
        else:
            raw_keys_to_delete.append(original_key)

    updates: list[tuple[str, str, str]] = []
    for normalized_key, (original_key, card_id) in desired_rows.items():
        if original_key == normalized_key:
            continue
        if strict:
            raise ConfigurationError(
                f"elite key {original_key} was not backfilled to policy-scoped identity"
            )
        updates.append((original_key, normalized_key, card_id))
    return updates, raw_keys_to_delete


def _normalize_card_payload(
    payload: dict[str, Any],
    *,
    card_id: str,
    strict: bool,
) -> tuple[dict[str, Any], bool]:
    normalized = dict(payload)
    cell_id = normalized.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id:
        raise ConfigurationError(f"frontier card {card_id} cell_id is required")

    changed = False
    policy_id = normalized.get("domain_policy_id")
    supplied_archive_key = normalized.get("archive_cell_key")
    if policy_id is None:
        if strict:
            raise ConfigurationError(
                f"frontier card {card_id} is missing domain_policy_id after migration 006"
            )
        if supplied_archive_key is not None:
            raise ConfigurationError(
                f"frontier card {card_id} legacy card requires explicit domain_policy_id"
            )
        if cell_id not in FINANCE_POLICY.universe():
            raise ConfigurationError(
                f"frontier card {card_id} legacy card requires explicit domain_policy_id"
            )
        policy = FINANCE_POLICY
        normalized["domain_policy_id"] = policy.policy_id
        changed = True
    else:
        normalized_policy_id = _normalize_policy_id(policy_id, label=f"frontier card {card_id}")
        policy = get_policy(normalized_policy_id)
        if normalized_policy_id != policy_id:
            normalized["domain_policy_id"] = normalized_policy_id
            changed = True

    if cell_id not in policy.universe():
        raise ConfigurationError(
            f"frontier card {card_id} cell_id is outside the registered policy universe"
        )

    derived_archive_key = archive_cell_key(domain_policy_id=policy.policy_id, cell_id=cell_id)
    if supplied_archive_key is not None and supplied_archive_key != derived_archive_key:
        raise ConfigurationError(
            f"frontier card {card_id} archive_cell_key does not match the policy-scoped cell key"
        )
    if supplied_archive_key != derived_archive_key:
        if strict:
            raise ConfigurationError(
                f"frontier card {card_id} archive_cell_key is missing after migration 006"
            )
        normalized["archive_cell_key"] = derived_archive_key
        changed = True
    return normalized, changed


def _normalize_elite_key(original_key: str, *, strict: bool) -> str:
    if "::" in original_key:
        policy_id, raw_cell_id = original_key.split("::", 1)
        normalized_policy_id = _normalize_policy_id(policy_id, label=f"elite key {original_key}")
        policy = get_policy(normalized_policy_id)
        if raw_cell_id not in policy.universe():
            raise ConfigurationError(
                f"elite key {original_key} cell_id is outside the registered policy universe"
            )
        return archive_cell_key(domain_policy_id=policy.policy_id, cell_id=raw_cell_id)
    if original_key not in FINANCE_POLICY.universe():
        raise ConfigurationError(
            f"elite key {original_key} cannot be mapped into the finance/1 archive universe"
        )
    if strict:
        raise ConfigurationError(
            f"elite key {original_key} was not backfilled to policy-scoped identity"
        )
    return archive_cell_key(domain_policy_id=FINANCE_POLICY.policy_id, cell_id=original_key)


def _require_candidate_maps_to_policy(
    candidate: dict[str, Any],
    *,
    policy_id: str,
    label: str,
) -> None:
    descriptor = candidate.get("research_descriptor")
    if not isinstance(descriptor, dict):
        raise ConfigurationError(f"{label} research_descriptor is required for policy backfill")
    policy = get_policy(policy_id)
    try:
        policy.cell_id(descriptor)
    except ValueError as exc:
        raise ConfigurationError(
            f"{label} cannot be mapped into the {policy.policy_id} universe"
        ) from exc


def _normalize_policy_id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} domain_policy_id must be a non-empty string")
    try:
        return get_policy(value.strip()).policy_id
    except ValueError as exc:
        raise ConfigurationError(f"{label} has unknown domain_policy_id: {value}") from exc


def _load_json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{label} payload_json is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError(f"{label} payload_json must decode to an object")
    return payload


def _dump_json_object(payload: dict[str, Any], *, label: str) -> str:
    try:
        return json.dumps(payload)
    except TypeError as exc:
        raise ConfigurationError(f"{label} payload_json is not serializable") from exc
