from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from papers.infra.piccolo.database import PiccoloDatabase
from research.catalog.models import CatalogError, VerifiedRun


@dataclass(frozen=True, slots=True)
class StoredRun:
    run_id: str
    bundle_path: str
    record: VerifiedRun


@dataclass(frozen=True, slots=True)
class CatalogStore:
    database: PiccoloDatabase

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[StoredRun, ...]:
        if not 1 <= limit <= 100 or offset < 0:
            raise CatalogError("Catalog pagination requires limit 1..100 and nonnegative offset")
        if not self.database.path.exists():
            return ()
        with sqlite3.connect(f"file:{self.database.path}?mode=ro", uri=True) as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_run_catalog'"
                ).fetchone()
                is None
            ):
                return ()
            rows = connection.execute(
                "SELECT run_id, bundle_path, document_json FROM "
                "research_run_catalog ORDER BY indexed_at, run_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return tuple(
            StoredRun(str(row[0]), str(row[1]), VerifiedRun.model_validate_json(row[2]))
            for row in rows
        )

    def get(self, run_id: str) -> StoredRun:
        if self.database.path.exists():
            with sqlite3.connect(f"file:{self.database.path}?mode=ro", uri=True) as connection:
                if connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_run_catalog'"
                ).fetchone():
                    row = connection.execute(
                        "SELECT bundle_path, document_json FROM "
                        "research_run_catalog WHERE run_id=?",
                        (run_id,),
                    ).fetchone()
                    if row is not None:
                        return StoredRun(
                            run_id, str(row[0]), VerifiedRun.model_validate_json(row[1])
                        )
        raise CatalogError("Research run is not indexed")

    def put(self, bundle_path: str, record: VerifiedRun) -> StoredRun:
        self.database.path.parent.mkdir(parents=True, exist_ok=True)
        raw = record.model_dump_json()
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS research_run_catalog (run_id "
                "TEXT PRIMARY KEY, bundle_path TEXT NOT NULL, document_json "
                "TEXT NOT NULL, indexed_at TEXT NOT NULL)"
            )
            previous = connection.execute(
                "SELECT document_json FROM research_run_catalog WHERE run_id=?", (record.run_id,)
            ).fetchone()
            if previous is not None and VerifiedRun.model_validate_json(previous[0]) != record:
                raise CatalogError("Verified run identity changed for an indexed artifact")
            connection.execute(
                "INSERT INTO "
                "research_run_catalog(run_id,bundle_path,document_json,indexed_at) "
                "VALUES(?,?,?,?) ON CONFLICT(run_id) "
                "DO UPDATE SET bundle_path=excluded.bundle_path",
                (record.run_id, bundle_path, raw, datetime.now(UTC).isoformat()),
            )
        return StoredRun(record.run_id, bundle_path, record)
