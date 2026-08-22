from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from nsqd.infra.piccolo.schema import NSQD_TABLE_DDL
from papers.domain.errors import ConfigurationError
from papers.infra.piccolo.database import _TABLES, PiccoloDatabase

_NOW = datetime.now(UTC).isoformat()
_JOB_COLUMNS = (
    "job_id, type, status, paper_id, run_id, payload_json, "
    "attempts, max_attempts, run_after, last_error, created_at, updated_at"
)
_MIGRATION_006 = "006_nsqd_legacy_finance_policy_backfill"
_MIGRATION_007 = "007_nsqd_map_job_type"
_MIGRATION_008 = "008_nsqd_acquisition_cycles"
_FINANCE_CELL_ID = "mechanism=flow-driven|target=drawdown|horizon=intraday"
_OPTIMIZATION_CELL_ID = (
    "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"
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


def _policy_verdict_columns(db: PiccoloDatabase) -> list[dict[str, object]]:
    return [dict(row) for row in db.fetchall("PRAGMA table_info(nsqd_policy_verdicts)")]


def _prepare_legacy_policy_database(path: Path) -> PiccoloDatabase:
    db = PiccoloDatabase(path)
    db.initialize_schema()
    db.execute("DELETE FROM schema_migrations WHERE version = ?", [_MIGRATION_006])
    return db


def _downgrade_nsqd_jobs_to_legacy(db: PiccoloDatabase) -> None:
    db.execute("DELETE FROM schema_migrations WHERE version = ?", [_MIGRATION_007])
    db.execute("ALTER TABLE nsqd_jobs RENAME TO nsqd_jobs_old")
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
        INSERT INTO nsqd_jobs
        SELECT job_id, type, status, payload_json, attempts, max_attempts,
               run_after, last_error, created_at, updated_at
        FROM nsqd_jobs_old
        """
    )
    db.execute("DROP TABLE nsqd_jobs_old")


def _dump_json(payload: dict[str, object]) -> str:
    return json.dumps(payload)


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
    assert versions == {
        "001_baseline",
        "002_job_integrity_check",
        "003_nsqd_tables",
        "004_nsqd_snapshot_versions",
        "005_nsqd_policy_verdicts",
        _MIGRATION_006,
        _MIGRATION_007,
        _MIGRATION_008,
    }
    assert "CHECK" in _jobs_sql(db).upper()
    assert _policy_verdict_columns(db) == [
        {
            "cid": 0,
            "name": "snapshot_id",
            "type": "VARCHAR",
            "notnull": 1,
            "dflt_value": None,
            "pk": 1,
        },
        {
            "cid": 1,
            "name": "domain_policy_id",
            "type": "VARCHAR",
            "notnull": 1,
            "dflt_value": None,
            "pk": 2,
        },
        {"cid": 2, "name": "verdict", "type": "TEXT", "notnull": 1, "dflt_value": None, "pk": 0},
    ]
    db.initialize_schema()
    again = db.fetchall("SELECT version FROM schema_migrations")
    assert len(again) == 8


def test_map_job_migration_upgrades_existing_nsqd_jobs_check_and_preserves_rows(
    tmp_path: Path,
) -> None:
    db = PiccoloDatabase(tmp_path / "map-job-upgrade.sqlite")
    db.initialize_schema()
    _downgrade_nsqd_jobs_to_legacy(db)
    db.execute(
        """
        INSERT INTO nsqd_jobs (
            job_id, type, status, payload_json, attempts, max_attempts,
            run_after, last_error, created_at, updated_at
        ) VALUES (?, 'score', 'queued', ?, 1, 3, NULL, 'note', ?, ?)
        """,
        ["job-score", '{"k":"v"}', _NOW, _NOW],
    )

    db.initialize_schema()

    sql = db.fetchone("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_jobs'")
    assert sql is not None
    assert "'map'" in str(sql["sql"])
    row = db.fetchone(
        "SELECT type, status, payload_json, attempts, max_attempts, last_error "
        "FROM nsqd_jobs WHERE job_id = ?",
        ["job-score"],
    )
    assert row == {
        "type": "score",
        "status": "queued",
        "payload_json": '{"k":"v"}',
        "attempts": 1,
        "max_attempts": 3,
        "last_error": "note",
    }
    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_007])
        is not None
    )


def test_map_job_migration_rolls_back_when_copy_fails(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "map-job-rollback.sqlite")
    db.initialize_schema()
    _downgrade_nsqd_jobs_to_legacy(db)
    db.execute(
        """
        INSERT INTO nsqd_jobs (
            job_id, type, status, payload_json, attempts, max_attempts,
            run_after, last_error, created_at, updated_at
        ) VALUES (?, 'score', 'queued', ?, 1, 3, NULL, 'note', ?, ?)
        """,
        ["job-score", '{"k":"v"}', _NOW, _NOW],
    )
    original = db.fetchone(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_jobs'"
    )
    assert original is not None

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("nsqd job copy aborted")

    with (
        patch(
            "papers.infra.piccolo.migrations.runner.copy_nsqd_jobs_into_new_table",
            new=boom,
        ),
        pytest.raises(RuntimeError, match="nsqd job copy aborted"),
    ):
        db.initialize_schema()

    after = db.fetchone("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_jobs'")
    assert after == original
    assert db.fetchone("SELECT job_id FROM nsqd_jobs WHERE job_id = ?", ["job-score"]) is not None
    assert db.fetchone("SELECT name FROM sqlite_schema WHERE name = 'new_nsqd_jobs'") is None
    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_007])
        is None
    )


def test_map_job_migration_recovers_when_new_check_already_applied_without_ledger_row(
    tmp_path: Path,
) -> None:
    db = PiccoloDatabase(tmp_path / "map-job-recover.sqlite")
    db.initialize_schema()
    db.execute("DELETE FROM schema_migrations WHERE version = ?", [_MIGRATION_007])

    db.initialize_schema()

    sql = db.fetchone("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'nsqd_jobs'")
    assert sql is not None
    assert "'map'" in str(sql["sql"])
    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_007])
        is not None
    )


def test_map_job_migration_rejects_malformed_existing_applied_schema(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "map-job-malformed-applied.sqlite")
    db.initialize_schema()
    db.execute("DROP TABLE nsqd_jobs")
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
            CHECK (type IN ('harvest','project','diverge','ground','score')),
            CHECK (status IN ('queued','running','succeeded','failed','canceled'))
        )
        """
    )

    with pytest.raises(ConfigurationError, match="nsqd_jobs schema mismatch"):
        db.initialize_schema()


def test_policy_backfill_migration_upgrades_legacy_finance_rows_and_is_idempotent(
    tmp_path: Path,
) -> None:
    db = _prepare_legacy_policy_database(tmp_path / "legacy-finance.sqlite")
    legacy_record = {
        "record_id": "record-fin-1",
        "content_hash": "hash-fin-1",
        "snapshots": ["snap-1"],
        "type": "paper",
        "source": "doi:10.1/fin",
        "paraphrase": "legacy finance record",
    }
    legacy_candidate = {
        "candidate": {
            "title": "legacy finance candidate",
            "research_descriptor": {
                "mechanism": "flow-driven",
                "target": "drawdown",
                "horizon": "intraday",
            },
        },
        "axiom": "legacy axiom",
        "generator_run_id": "gen-1",
    }
    legacy_card = {
        "card_id": "legacy-card",
        "cell_id": _FINANCE_CELL_ID,
        "title": "legacy finance card",
        "generating_operator": "A",
        "snapshot_id": "snap-1",
        "corpus_version": 1,
        "viability": 5,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "artifact-fin-1",
        "card_decision": "accepted",
    }
    db.execute(
        "INSERT INTO nsqd_corpus_records (record_id, payload_json) VALUES (?, ?)",
        ["record-fin-1", _dump_json(legacy_record)],
    )
    db.execute(
        "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
        ["artifact-fin-1", _dump_json(legacy_candidate)],
    )
    db.execute(
        "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) VALUES (?, ?, ?)",
        ["legacy-card", _FINANCE_CELL_ID, _dump_json(legacy_card)],
    )
    db.execute(
        "INSERT INTO nsqd_elites (cell_id, card_id) VALUES (?, ?)",
        [_FINANCE_CELL_ID, "legacy-card"],
    )

    db.initialize_schema()

    record_row = db.fetchone(
        "SELECT payload_json FROM nsqd_corpus_records WHERE record_id = ?",
        ["record-fin-1"],
    )
    candidate_row = db.fetchone(
        "SELECT payload_json FROM nsqd_candidates WHERE artifact_hash = ?",
        ["artifact-fin-1"],
    )
    card_row = db.fetchone(
        "SELECT cell_id, payload_json FROM nsqd_frontier_cards WHERE card_id = ?",
        ["legacy-card"],
    )
    elite_row = db.fetchone(
        "SELECT cell_id, card_id FROM nsqd_elites WHERE card_id = ?",
        ["legacy-card"],
    )
    assert record_row is not None
    assert candidate_row is not None
    assert card_row is not None
    assert elite_row is not None

    record_payload = json.loads(str(record_row["payload_json"]))
    candidate_payload = json.loads(str(candidate_row["payload_json"]))
    card_payload = json.loads(str(card_row["payload_json"]))
    assert record_payload == {**legacy_record, "domain_policy_id": "finance/1"}
    assert candidate_payload == {
        **legacy_candidate,
        "candidate": {
            **legacy_candidate["candidate"],
            "domain_policy_id": "finance/1",
        },
    }
    assert card_payload == {
        **legacy_card,
        "domain_policy_id": "finance/1",
        "archive_cell_key": f"finance/1::{_FINANCE_CELL_ID}",
    }
    assert card_payload["cell_id"] == _FINANCE_CELL_ID
    assert card_row["cell_id"] == _FINANCE_CELL_ID
    assert elite_row == {
        "cell_id": f"finance/1::{_FINANCE_CELL_ID}",
        "card_id": "legacy-card",
    }
    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert _MIGRATION_006 in versions

    db.initialize_schema()

    assert (
        db.fetchone(
            "SELECT payload_json FROM nsqd_corpus_records WHERE record_id = ?",
            ["record-fin-1"],
        )
        == record_row
    )
    assert (
        db.fetchone(
            "SELECT payload_json FROM nsqd_candidates WHERE artifact_hash = ?",
            ["artifact-fin-1"],
        )
        == candidate_row
    )
    assert (
        db.fetchone(
            "SELECT cell_id, payload_json FROM nsqd_frontier_cards WHERE card_id = ?",
            ["legacy-card"],
        )
        == card_row
    )
    assert (
        db.fetchone(
            "SELECT cell_id, card_id FROM nsqd_elites WHERE card_id = ?",
            ["legacy-card"],
        )
        == elite_row
    )
    assert len(db.fetchall("SELECT version FROM schema_migrations")) == 8


def test_policy_backfill_migration_rejects_candidate_outside_finance_universe(
    tmp_path: Path,
) -> None:
    db = _prepare_legacy_policy_database(tmp_path / "legacy-candidate-invalid.sqlite")
    db.execute(
        "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
        [
            "artifact-opt-1",
            _dump_json(
                {
                    "candidate": {
                        "title": "legacy optimization candidate",
                        "research_descriptor": {
                            "problem": "constrained-expectation",
                            "method": "sequential-quadratic",
                            "setting": "rank-deficient",
                        },
                    },
                    "axiom": "legacy axiom",
                    "generator_run_id": "gen-1",
                }
            ),
        ],
    )

    with pytest.raises(ConfigurationError, match="artifact-opt-1"):
        db.initialize_schema()

    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_006])
        is None
    )


def test_policy_backfill_migration_rejects_tagged_candidate_outside_policy_universe(
    tmp_path: Path,
) -> None:
    db = _prepare_legacy_policy_database(tmp_path / "tagged-candidate-invalid.sqlite")
    db.execute(
        "INSERT INTO nsqd_candidates (artifact_hash, payload_json) VALUES (?, ?)",
        [
            "artifact-fin-bad-1",
            _dump_json(
                {
                    "candidate": {
                        "title": "tagged finance candidate with optimization descriptor",
                        "domain_policy_id": "finance/1",
                        "research_descriptor": {
                            "problem": "constrained-expectation",
                            "method": "sequential-quadratic",
                            "setting": "rank-deficient",
                        },
                    },
                    "axiom": "legacy axiom",
                    "generator_run_id": "gen-1",
                }
            ),
        ],
    )

    with pytest.raises(ConfigurationError, match="artifact-fin-bad-1"):
        db.initialize_schema()

    stored = db.fetchone(
        "SELECT payload_json FROM nsqd_candidates WHERE artifact_hash = ?",
        ["artifact-fin-bad-1"],
    )
    assert stored is not None
    assert json.loads(str(stored["payload_json"])) == {
        "candidate": {
            "title": "tagged finance candidate with optimization descriptor",
            "domain_policy_id": "finance/1",
            "research_descriptor": {
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
        },
        "axiom": "legacy axiom",
        "generator_run_id": "gen-1",
    }
    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_006])
        is None
    )


def test_policy_backfill_migration_rejects_legacy_card_outside_finance_universe(
    tmp_path: Path,
) -> None:
    db = _prepare_legacy_policy_database(tmp_path / "legacy-card-invalid.sqlite")
    db.execute(
        "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) VALUES (?, ?, ?)",
        [
            "legacy-opt-card",
            _OPTIMIZATION_CELL_ID,
            _dump_json(
                {
                    "card_id": "legacy-opt-card",
                    "cell_id": _OPTIMIZATION_CELL_ID,
                    "title": "legacy optimization card",
                    "generating_operator": "A",
                    "snapshot_id": "snap-1",
                    "corpus_version": 1,
                    "viability": 5,
                    "nov": 1,
                    "mech": 5,
                    "fals": 5,
                    "dpred": 5,
                    "dval": 5,
                    "candidate_artifact_hash": "artifact-opt-1",
                    "card_decision": "accepted",
                }
            ),
        ],
    )

    with pytest.raises(ConfigurationError, match="legacy-opt-card"):
        db.initialize_schema()

    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_006])
        is None
    )


def test_policy_backfill_migration_rejects_conflicting_scoped_elite(tmp_path: Path) -> None:
    db = _prepare_legacy_policy_database(tmp_path / "legacy-elite-conflict.sqlite")
    scoped_key = f"finance/1::{_FINANCE_CELL_ID}"
    explicit_card = {
        "card_id": "explicit-card",
        "domain_policy_id": "finance/1",
        "cell_id": _FINANCE_CELL_ID,
        "archive_cell_key": scoped_key,
        "title": "explicit finance card",
        "generating_operator": "A",
        "snapshot_id": "snap-1",
        "corpus_version": 1,
        "viability": 5,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "artifact-fin-2",
        "card_decision": "accepted",
    }
    db.execute(
        "INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json) "
        "VALUES (?, ?, ?), (?, ?, ?)",
        [
            "legacy-card",
            _FINANCE_CELL_ID,
            _dump_json(
                {
                    "card_id": "legacy-card",
                    "cell_id": _FINANCE_CELL_ID,
                    "title": "legacy finance card",
                    "generating_operator": "A",
                    "snapshot_id": "snap-1",
                    "corpus_version": 1,
                    "viability": 5,
                    "nov": 1,
                    "mech": 5,
                    "fals": 5,
                    "dpred": 5,
                    "dval": 5,
                    "candidate_artifact_hash": "artifact-fin-1",
                    "card_decision": "accepted",
                }
            ),
            "explicit-card",
            _FINANCE_CELL_ID,
            _dump_json(explicit_card),
        ],
    )
    db.execute(
        "INSERT INTO nsqd_elites (cell_id, card_id) VALUES (?, ?), (?, ?)",
        [_FINANCE_CELL_ID, "legacy-card", scoped_key, "explicit-card"],
    )

    with pytest.raises(ConfigurationError, match="conflicting scoped elite"):
        db.initialize_schema()

    elite_rows = db.fetchall("SELECT cell_id, card_id FROM nsqd_elites ORDER BY cell_id")
    assert elite_rows == [
        {"cell_id": scoped_key, "card_id": "explicit-card"},
        {"cell_id": _FINANCE_CELL_ID, "card_id": "legacy-card"},
    ]
    assert (
        db.fetchone("SELECT version FROM schema_migrations WHERE version = ?", [_MIGRATION_006])
        is None
    )


def test_policy_verdict_migration_recovers_when_table_exists_without_ledger_row(
    tmp_path: Path,
) -> None:
    db = PiccoloDatabase(tmp_path / "policy-verdict-recover.sqlite")
    db.initialize_schema()
    db.execute("DELETE FROM schema_migrations WHERE version = ?", ["005_nsqd_policy_verdicts"])

    db.initialize_schema()

    assert _policy_verdict_columns(db) == [
        {
            "cid": 0,
            "name": "snapshot_id",
            "type": "VARCHAR",
            "notnull": 1,
            "dflt_value": None,
            "pk": 1,
        },
        {
            "cid": 1,
            "name": "domain_policy_id",
            "type": "VARCHAR",
            "notnull": 1,
            "dflt_value": None,
            "pk": 2,
        },
        {"cid": 2, "name": "verdict", "type": "TEXT", "notnull": 1, "dflt_value": None, "pk": 0},
    ]
    assert (
        db.fetchone(
            "SELECT version FROM schema_migrations WHERE version = '005_nsqd_policy_verdicts'"
        )
        is not None
    )


def test_policy_verdict_migration_rejects_malformed_existing_table_without_recording_005(
    tmp_path: Path,
) -> None:
    db = PiccoloDatabase(tmp_path / "policy-verdict-malformed.sqlite")
    db.initialize_schema()
    db.execute("DELETE FROM schema_migrations WHERE version = ?", ["005_nsqd_policy_verdicts"])
    db.execute("DROP TABLE nsqd_policy_verdicts")
    db.execute(
        """
        CREATE TABLE nsqd_policy_verdicts (
            domain_policy_id VARCHAR NOT NULL,
            snapshot_id VARCHAR NOT NULL,
            verdict TEXT,
            PRIMARY KEY (domain_policy_id, snapshot_id)
        )
        """
    )

    with pytest.raises(ConfigurationError, match="policy verdict schema mismatch"):
        db.initialize_schema()

    assert (
        db.fetchone(
            "SELECT version FROM schema_migrations WHERE version = '005_nsqd_policy_verdicts'"
        )
        is None
    )


def test_policy_verdict_migration_rejects_malformed_applied_schema(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "policy-verdict-applied.sqlite")
    db.initialize_schema()
    db.execute("DROP TABLE nsqd_policy_verdicts")
    db.execute(
        """
        CREATE TABLE nsqd_policy_verdicts (
            snapshot_id VARCHAR NOT NULL,
            domain_policy_id VARCHAR,
            verdict TEXT NOT NULL,
            PRIMARY KEY (domain_policy_id, snapshot_id)
        )
        """
    )

    with pytest.raises(ConfigurationError, match="policy verdict schema mismatch"):
        db.initialize_schema()


def test_snapshot_version_migration_preserves_existing_snapshots(tmp_path: Path) -> None:
    db = _build_previous_baseline(tmp_path / "snapshot-version.sqlite")
    db.execute(
        """
        CREATE TABLE schema_migrations (
            version VARCHAR(255) PRIMARY KEY NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    for version in ("001_baseline", "002_job_integrity_check", "003_nsqd_tables"):
        db.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            [version, _NOW],
        )
    for statement in NSQD_TABLE_DDL:
        db.execute(statement)
    db.execute(
        """
        INSERT INTO nsqd_corpus_snapshots (snapshot_id, schema_version, record_ids_json)
        VALUES (?, ?, ?), (?, ?, ?)
        """,
        ["snap-a", 1, "[]", "snap-b", 1, "[]"],
    )

    db.initialize_schema()

    rows = db.fetchall(
        "SELECT snapshot_id, corpus_version FROM nsqd_corpus_snapshots ORDER BY corpus_version"
    )
    assert rows == [
        {"snapshot_id": "snap-a", "corpus_version": 1},
        {"snapshot_id": "snap-b", "corpus_version": 2},
    ]
    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert "004_nsqd_snapshot_versions" in versions


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
        "nsqd_policy_verdicts",
        "nsqd_acquisition_cycles",
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
