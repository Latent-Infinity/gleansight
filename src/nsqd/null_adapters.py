from __future__ import annotations

import math
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nsqd.domain.snapshot import is_utc_datetime
from nsqd.ports import NSQD_JOB_TYPES, CorpusHit, NsqdJob, NsqdJobType


@dataclass(frozen=True)
class FixedClock:
    as_of: datetime

    def __post_init__(self) -> None:
        _require_utc_datetime("as_of", self.as_of)

    def now(self) -> datetime:
        return self.as_of


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class NullCorpusRecordStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def put(self, record: dict[str, Any]) -> None:
        self._rows[str(record["record_id"])] = deepcopy(record)

    def get(self, record_id: str) -> dict[str, Any] | None:
        row = self._rows.get(record_id)
        return deepcopy(row) if row is not None else None

    def list_ids(self) -> list[str]:
        return sorted(self._rows)


class NullCorpusSnapshotStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def commit(self, snapshot_id: str, record_ids: list[str], schema_version: int) -> None:
        self._rows[snapshot_id] = {
            "snapshot_id": snapshot_id,
            "record_ids": deepcopy(record_ids),
            "schema_version": schema_version,
        }

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self._rows.get(snapshot_id)
        return deepcopy(row) if row is not None else None

    def record_ids(self, snapshot_id: str) -> list[str]:
        row = self._rows.get(snapshot_id)
        if row is None:
            return []
        return deepcopy(row["record_ids"])


class NullCorpusIndex:
    def __init__(self) -> None:
        self._vectors: dict[tuple[str, str], list[float]] = {}

    def upsert(self, snapshot_id: str, record_id: str, vector: list[float]) -> None:
        self._vectors[(snapshot_id, record_id)] = list(vector)

    def query(self, snapshot_id: str, vector: list[float], k: int) -> list[CorpusHit]:
        scored: list[tuple[str, float]] = []
        for (snap, record_id), stored in self._vectors.items():
            if snap != snapshot_id:
                continue
            scored.append((record_id, _cosine_distance(vector, stored)))
        scored.sort(key=lambda item: (item[1], item[0]))
        hits = [
            CorpusHit(record_id=record_id, distance=distance, rank=rank)
            for rank, (record_id, distance) in enumerate(scored[:k], start=1)
        ]
        return hits


class NullMorphospaceStore:
    def __init__(self) -> None:
        self._cells: dict[str, dict[str, Any]] = {}

    def mark_inspected(self, cell_id: str, inspected_at: datetime) -> None:
        _require_utc_datetime("inspected_at", inspected_at)
        self._cells[cell_id] = {"cell_id": cell_id, "inspected_at": inspected_at}

    def get_cell(self, cell_id: str) -> dict[str, Any] | None:
        row = self._cells.get(cell_id)
        return deepcopy(row) if row is not None else None


class NullNsqdCandidateStore:
    def __init__(self) -> None:
        self._artifacts: dict[str, dict[str, Any]] = {}

    def put_artifact(self, artifact_hash: str, payload: dict[str, Any]) -> None:
        self._artifacts[artifact_hash] = deepcopy(payload)

    def get_artifact(self, artifact_hash: str) -> dict[str, Any] | None:
        row = self._artifacts.get(artifact_hash)
        return deepcopy(row) if row is not None else None


class NullFrontierCardStore:
    def __init__(self) -> None:
        self._cards: dict[str, dict[str, Any]] = {}
        self._elites: dict[str, str] = {}

    def put_card(self, card: dict[str, Any]) -> None:
        self._cards[str(card["card_id"])] = deepcopy(card)

    def get_card(self, card_id: str) -> dict[str, Any] | None:
        row = self._cards.get(card_id)
        return deepcopy(row) if row is not None else None

    def elite_for_cell(self, cell_id: str) -> dict[str, Any] | None:
        card_id = self._elites.get(cell_id)
        if card_id is None:
            return None
        return self.get_card(card_id)

    def set_elite(self, cell_id: str, card_id: str | None) -> None:
        if card_id is None:
            self._elites.pop(cell_id, None)
            return
        self._elites[cell_id] = card_id


@dataclass
class _JobRow:
    job: NsqdJob
    error: str | None = None
    canceled: bool = False


class NullNsqdJobQueue:
    def __init__(self, *, max_attempts: int = 3) -> None:
        self._max_attempts = max_attempts
        self._jobs: dict[str, _JobRow] = {}

    def enqueue(
        self,
        type: NsqdJobType,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        _require_job_type(type)
        if run_after is not None:
            _require_utc_datetime("run_after", run_after)
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = _JobRow(
            job=NsqdJob(
                job_id=job_id,
                type=type,
                status="queued",
                payload=deepcopy(payload),
                attempts=0,
                max_attempts=self._max_attempts,
                run_after=run_after,
            )
        )
        return job_id

    def claim_next(self, now: datetime) -> NsqdJob | None:
        _require_utc_datetime("now", now)
        eligible = [
            row
            for row in self._jobs.values()
            if not row.canceled
            and row.job.status == "queued"
            and (row.job.run_after is None or row.job.run_after <= now)
            and row.job.attempts < row.job.max_attempts
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda row: row.job.job_id)
        row = eligible[0]
        claimed = NsqdJob(
            job_id=row.job.job_id,
            type=row.job.type,
            status="running",
            payload=deepcopy(row.job.payload),
            attempts=row.job.attempts + 1,
            max_attempts=row.job.max_attempts,
            run_after=row.job.run_after,
        )
        row.job = claimed
        return deepcopy(claimed)

    def mark_succeeded(self, job_id: str) -> None:
        self._set_status(job_id, "succeeded")

    def mark_retryable(self, job_id: str, error: str, run_after: datetime) -> None:
        _require_utc_datetime("run_after", run_after)
        row = self._jobs[job_id]
        row.error = error
        row.job = NsqdJob(
            job_id=row.job.job_id,
            type=row.job.type,
            status="queued",
            payload=deepcopy(row.job.payload),
            attempts=row.job.attempts,
            max_attempts=row.job.max_attempts,
            run_after=run_after,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        row = self._jobs[job_id]
        row.error = error
        self._set_status(job_id, "failed")

    def cancel(self, job_id: str) -> None:
        row = self._jobs[job_id]
        row.canceled = True
        self._set_status(job_id, "canceled")

    def _set_status(self, job_id: str, status: str) -> None:
        row = self._jobs[job_id]
        row.job = NsqdJob(
            job_id=row.job.job_id,
            type=row.job.type,
            status=status,
            payload=deepcopy(row.job.payload),
            attempts=row.job.attempts,
            max_attempts=row.job.max_attempts,
            run_after=row.job.run_after,
        )


def _require_utc_datetime(name: str, value: datetime) -> None:
    if not is_utc_datetime(value):
        raise ValueError(f"{name} must be a UTC datetime")


def _require_job_type(job_type: str) -> None:
    if job_type not in NSQD_JOB_TYPES:
        raise ValueError(f"unknown job type: {job_type}")


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 1.0
    similarity = dot / (norm_l * norm_r)
    return 1.0 - similarity
