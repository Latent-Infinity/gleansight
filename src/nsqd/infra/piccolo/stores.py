from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from piccolo.engine.sqlite import TransactionType
from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

from nsqd.domain.harvest import HarvestRejected, immutable_record_conflict
from nsqd.domain.snapshot import is_utc_datetime, snapshot_id
from nsqd.ports import NSQD_JOB_TYPES, HarvestCommit, NsqdJob, NsqdJobType
from papers.infra.piccolo.database import PiccoloDatabase


def _require_utc_datetime(name: str, value: datetime) -> None:
    if not is_utc_datetime(value):
        raise ValueError(f"{name} must be a UTC datetime")


def _require_job_type(job_type: str) -> None:
    if job_type not in NSQD_JOB_TYPES:
        raise ValueError(f"unknown job type: {job_type}")


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _loads(raw: str) -> dict[str, Any]:
    loaded = json.loads(raw)
    assert isinstance(loaded, dict)
    return loaded


class PiccoloCorpusRecordStore:
    def __init__(self, database: PiccoloDatabase) -> None:
        self._db = database

    def put(self, record: dict[str, Any]) -> None:
        record_id = str(record["record_id"])
        payload = _dumps(record)
        self._db.execute(
            """
            INSERT OR IGNORE INTO nsqd_corpus_records (record_id, payload_json)
            VALUES (?, ?)
            """,
            [record_id, payload],
        )
        existing = self.get(record_id)
        if existing is None:
            raise RuntimeError("record commit did not persist")
        if existing != record:
            raise ValueError("record_id already committed with different content")

    def get(self, record_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT payload_json FROM nsqd_corpus_records WHERE record_id = ?",
            [record_id],
        )
        if row is None:
            return None
        return _loads(str(row["payload_json"]))

    def list_ids(self) -> list[str]:
        rows = self._db.fetchall("SELECT record_id FROM nsqd_corpus_records ORDER BY record_id")
        return [str(row["record_id"]) for row in rows]


class PiccoloCorpusSnapshotStore:
    def __init__(self, database: PiccoloDatabase) -> None:
        self._db = database

    def commit(self, snapshot_id: str, record_ids: list[str], schema_version: int) -> int:
        payload = json.dumps(list(record_ids))
        self._db.execute(
            """
            INSERT OR IGNORE INTO nsqd_corpus_snapshots (
                snapshot_id, schema_version, record_ids_json, corpus_version
            )
            SELECT ?, ?, ?, COALESCE(MAX(corpus_version), 0) + 1
            FROM nsqd_corpus_snapshots
            """,
            [snapshot_id, schema_version, payload],
        )
        existing = self._db.fetchone(
            """
            SELECT corpus_version, schema_version, record_ids_json
            FROM nsqd_corpus_snapshots
            WHERE snapshot_id = ?
            """,
            [snapshot_id],
        )
        if existing is None:
            raise RuntimeError("snapshot commit did not persist")
        if (
            int(existing["schema_version"]) != schema_version
            or str(existing["record_ids_json"]) != payload
        ):
            raise ValueError("snapshot_id already committed with different content")
        return int(existing["corpus_version"])

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            """
            SELECT corpus_version, snapshot_id, schema_version, record_ids_json
            FROM nsqd_corpus_snapshots
            WHERE snapshot_id = ?
            """,
            [snapshot_id],
        )
        if row is None:
            return None
        return {
            "snapshot_id": str(row["snapshot_id"]),
            "record_ids": json.loads(str(row["record_ids_json"])),
            "schema_version": int(row["schema_version"]),
            "corpus_version": int(row["corpus_version"]),
        }

    def record_ids(self, snapshot_id: str) -> list[str]:
        row = self.get(snapshot_id)
        if row is None:
            return []
        ids = row["record_ids"]
        assert isinstance(ids, list)
        return [str(item) for item in ids]


class PiccoloHarvestStore:
    def __init__(self, database: PiccoloDatabase) -> None:
        self._db = database

    def commit(self, records: list[dict[str, Any]], schema_version: int) -> HarvestCommit:
        async def commit_in_transaction() -> HarvestCommit:
            async with self._db.engine.transaction(transaction_type=TransactionType.immediate):
                committed_ids: list[str] = []
                for record in records:
                    record_id = str(record["record_id"])
                    rows = await self._db.engine.run_querystring(
                        QueryString(
                            "SELECT payload_json FROM nsqd_corpus_records WHERE record_id = {}",
                            record_id,
                        )
                    )
                    if rows:
                        existing = _loads(str(rows[0]["payload_json"]))
                        conflict = immutable_record_conflict(existing, record)
                        if conflict is not None:
                            raise HarvestRejected(conflict)
                    else:
                        await self._db.engine.run_querystring(
                            QueryString(
                                """
                                INSERT INTO nsqd_corpus_records (record_id, payload_json)
                                VALUES ({}, {})
                                """,
                                record_id,
                                _dumps(record),
                            )
                        )
                    if record_id not in committed_ids:
                        committed_ids.append(record_id)

                all_rows = await self._db.engine.run_querystring(
                    QueryString(
                        "SELECT record_id, payload_json FROM nsqd_corpus_records ORDER BY record_id"
                    )
                )
                snapshot_rows = [
                    {
                        "record_id": str(row["record_id"]),
                        "content_hash": str(_loads(str(row["payload_json"]))["content_hash"]),
                    }
                    for row in all_rows
                ]
                committed_snapshot_id = snapshot_id(
                    records=snapshot_rows, schema_version=schema_version
                )
                snapshot_record_ids = [row["record_id"] for row in snapshot_rows]
                record_ids_json = json.dumps(snapshot_record_ids)
                existing_snapshots = await self._db.engine.run_querystring(
                    QueryString(
                        """
                        SELECT corpus_version, schema_version, record_ids_json
                        FROM nsqd_corpus_snapshots WHERE snapshot_id = {}
                        """,
                        committed_snapshot_id,
                    )
                )
                if existing_snapshots:
                    existing_snapshot = existing_snapshots[0]
                    if (
                        int(existing_snapshot["schema_version"]) != schema_version
                        or str(existing_snapshot["record_ids_json"]) != record_ids_json
                    ):
                        raise ValueError("snapshot_id already committed with different content")
                    corpus_version = int(existing_snapshot["corpus_version"])
                else:
                    await self._db.engine.run_querystring(
                        QueryString(
                            """
                            INSERT INTO nsqd_corpus_snapshots (
                                snapshot_id, schema_version, record_ids_json, corpus_version
                            )
                            SELECT {}, {}, {}, COALESCE(MAX(corpus_version), 0) + 1
                            FROM nsqd_corpus_snapshots
                            """,
                            committed_snapshot_id,
                            schema_version,
                            record_ids_json,
                        )
                    )
                    version_rows = await self._db.engine.run_querystring(
                        QueryString(
                            """
                            SELECT corpus_version FROM nsqd_corpus_snapshots
                            WHERE snapshot_id = {}
                            """,
                            committed_snapshot_id,
                        )
                    )
                    if not version_rows:
                        raise RuntimeError("snapshot commit did not persist")
                    corpus_version = int(version_rows[0]["corpus_version"])

                return HarvestCommit(
                    record_ids=tuple(committed_ids),
                    snapshot_id=committed_snapshot_id,
                    corpus_version=corpus_version,
                )
            raise RuntimeError("harvest transaction did not complete")

        return run_sync(commit_in_transaction())


class PiccoloNsqdCandidateStore:
    def __init__(self, database: PiccoloDatabase) -> None:
        self._db = database

    def put_artifact_if_absent(self, artifact_hash: str, payload: dict[str, Any]) -> bool:
        row = self._db.fetchone(
            """
            INSERT OR IGNORE INTO nsqd_candidates (artifact_hash, payload_json)
            VALUES (?, ?)
            RETURNING artifact_hash
            """,
            [artifact_hash, _dumps(payload)],
        )
        return row is not None

    def put_artifact(self, artifact_hash: str, payload: dict[str, Any]) -> None:
        raw = _dumps(payload)
        self._db.execute(
            """
            INSERT INTO nsqd_candidates (artifact_hash, payload_json)
            VALUES (?, ?)
            ON CONFLICT(artifact_hash) DO UPDATE SET payload_json = excluded.payload_json
            """,
            [artifact_hash, raw],
        )

    def get_artifact(self, artifact_hash: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT payload_json FROM nsqd_candidates WHERE artifact_hash = ?",
            [artifact_hash],
        )
        if row is None:
            return None
        return _loads(str(row["payload_json"]))


class PiccoloFrontierCardStore:
    def __init__(self, database: PiccoloDatabase) -> None:
        self._db = database

    def put_card(self, card: dict[str, Any]) -> None:
        card_id = str(card["card_id"])
        cell_id = str(card["cell_id"])
        raw = _dumps(card)
        self._db.execute(
            """
            INSERT INTO nsqd_frontier_cards (card_id, cell_id, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                cell_id = excluded.cell_id,
                payload_json = excluded.payload_json
            """,
            [card_id, cell_id, raw],
        )

    def get_card(self, card_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT payload_json FROM nsqd_frontier_cards WHERE card_id = ?",
            [card_id],
        )
        if row is None:
            return None
        return _loads(str(row["payload_json"]))

    def elite_for_cell(self, cell_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT card_id FROM nsqd_elites WHERE cell_id = ?",
            [cell_id],
        )
        if row is None:
            return None
        return self.get_card(str(row["card_id"]))

    def set_elite(self, cell_id: str, card_id: str | None) -> None:
        self._db.execute("DELETE FROM nsqd_elites WHERE cell_id = ?", [cell_id])
        if card_id is None:
            return
        self._db.execute(
            "INSERT INTO nsqd_elites (cell_id, card_id) VALUES (?, ?)",
            [cell_id, card_id],
        )


class PiccoloMorphospaceStore:
    def __init__(self, database: PiccoloDatabase) -> None:
        self._db = database

    def mark_inspected(self, cell_id: str, inspected_at: datetime) -> None:
        _require_utc_datetime("inspected_at", inspected_at)
        self._db.execute(
            """
            INSERT INTO nsqd_morphospace (cell_id, inspected_at)
            VALUES (?, ?)
            ON CONFLICT(cell_id) DO UPDATE SET inspected_at = excluded.inspected_at
            """,
            [cell_id, inspected_at],
        )

    def get_cell(self, cell_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT cell_id, inspected_at FROM nsqd_morphospace WHERE cell_id = ?",
            [cell_id],
        )
        if row is None:
            return None
        return {"cell_id": str(row["cell_id"]), "inspected_at": row["inspected_at"]}


class PiccoloNsqdJobQueue:
    def __init__(self, database: PiccoloDatabase, *, max_attempts: int = 3) -> None:
        self._db = database
        self._engine = database.engine
        self._max_attempts = max_attempts

    def enqueue(
        self,
        type: NsqdJobType,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        _require_job_type(type)
        if run_after is not None:
            _require_utc_datetime("run_after", run_after)
        now = datetime.now(UTC)
        job_id = str(uuid.uuid4())
        self._db.execute(
            """
            INSERT INTO nsqd_jobs (
                job_id, type, status, payload_json, attempts, max_attempts,
                run_after, last_error, created_at, updated_at
            ) VALUES (?, ?, 'queued', ?, 0, ?, ?, NULL, ?, ?)
            """,
            [job_id, type, _dumps(payload), self._max_attempts, run_after, now, now],
        )
        return job_id

    def claim_next(self, now: datetime) -> NsqdJob | None:
        _require_utc_datetime("now", now)
        sql = """
            UPDATE nsqd_jobs
            SET status = 'running',
                attempts = attempts + 1,
                updated_at = {}
            WHERE job_id = (
                SELECT job_id
                FROM nsqd_jobs
                WHERE status = 'queued'
                  AND (run_after IS NULL OR run_after <= {})
                  AND attempts < max_attempts
                ORDER BY created_at, job_id
                LIMIT 1
            )
            RETURNING job_id, type, status, payload_json, attempts, max_attempts, run_after
        """
        rows = run_sync(self._engine.run_querystring(QueryString(sql, now, now)))
        if not rows:
            return None
        row = rows[0]
        return NsqdJob(
            job_id=str(row["job_id"]),
            type=row["type"],
            status=str(row["status"]),
            payload=_loads(str(row["payload_json"])),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            run_after=row["run_after"],
        )

    def claim_job(self, job_id: str, now: datetime) -> NsqdJob | None:
        _require_utc_datetime("now", now)
        sql = """
            UPDATE nsqd_jobs
            SET status = 'running',
                attempts = attempts + 1,
                updated_at = {}
            WHERE job_id = {}
              AND status = 'queued'
              AND (run_after IS NULL OR run_after <= {})
              AND attempts < max_attempts
            RETURNING job_id, type, status, payload_json, attempts, max_attempts, run_after
        """
        rows = run_sync(self._engine.run_querystring(QueryString(sql, now, job_id, now)))
        if not rows:
            return None
        row = rows[0]
        return NsqdJob(
            job_id=str(row["job_id"]),
            type=row["type"],
            status=str(row["status"]),
            payload=_loads(str(row["payload_json"])),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            run_after=row["run_after"],
        )

    def mark_succeeded(self, job_id: str) -> None:
        self._update_running_job(
            job_id,
            "SET status = 'succeeded', updated_at = ?",
            [datetime.now(UTC)],
        )

    def mark_retryable(self, job_id: str, error: str, run_after: datetime) -> None:
        _require_utc_datetime("run_after", run_after)
        self._update_running_job(
            job_id,
            "SET status = 'queued', last_error = ?, run_after = ?, updated_at = ?",
            [error, run_after, datetime.now(UTC)],
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        self._update_running_job(
            job_id,
            "SET status = 'failed', last_error = ?, updated_at = ?",
            [error, datetime.now(UTC)],
        )

    def cancel(self, job_id: str) -> None:
        self._db.execute(
            """
            UPDATE nsqd_jobs
            SET status = 'canceled', updated_at = ?
            WHERE job_id = ? AND status IN ('queued', 'running')
            """,
            [datetime.now(UTC), job_id],
        )

    def _update_running_job(self, job_id: str, set_clause: str, params: list[Any]) -> None:
        self._db.execute(
            f"UPDATE nsqd_jobs {set_clause} WHERE job_id = ? AND status = 'running'",
            [*params, job_id],
        )
