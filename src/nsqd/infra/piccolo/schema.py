from __future__ import annotations

import re

NSQD_TABLE_NAMES = (
    "nsqd_jobs",
    "nsqd_corpus_records",
    "nsqd_corpus_snapshots",
    "nsqd_candidates",
    "nsqd_frontier_cards",
    "nsqd_elites",
    "nsqd_morphospace",
)

NSQD_TABLE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS nsqd_jobs (
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
        CHECK (type IN ('harvest','project','diverge','ground','score','rescore','map')),
        CHECK (status IN ('queued','running','succeeded','failed','canceled'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nsqd_corpus_records (
        record_id VARCHAR PRIMARY KEY NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nsqd_corpus_snapshots (
        snapshot_id VARCHAR PRIMARY KEY NOT NULL,
        schema_version INTEGER NOT NULL,
        record_ids_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nsqd_candidates (
        artifact_hash VARCHAR PRIMARY KEY NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nsqd_frontier_cards (
        card_id VARCHAR PRIMARY KEY NOT NULL,
        cell_id VARCHAR NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nsqd_elites (
        cell_id VARCHAR PRIMARY KEY NOT NULL,
        card_id VARCHAR NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nsqd_morphospace (
        cell_id VARCHAR PRIMARY KEY NOT NULL,
        inspected_at TIMESTAMPTZ NOT NULL
    )
    """,
)

NSQD_TABLE_DDL_BY_NAME = dict(zip(NSQD_TABLE_NAMES, NSQD_TABLE_DDL, strict=True))


def normalize_create_table_sql(sql: str) -> tuple[str, ...]:
    tokens = tuple(re.findall(r"'[^']*'|[(),]|[^()\s,]+", sql.lower()))
    if tokens[:5] == ("create", "table", "if", "not", "exists"):
        return tuple(["create", "table", *tokens[5:]])
    return tokens
