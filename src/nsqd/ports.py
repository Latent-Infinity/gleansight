from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class CorpusHit:
    record_id: str
    distance: float
    rank: int


NsqdJobType = Literal["harvest", "project", "diverge", "ground", "score", "rescore"]
NSQD_JOB_TYPES: frozenset[str] = frozenset(
    {"harvest", "project", "diverge", "ground", "score", "rescore"}
)


@dataclass(frozen=True)
class NsqdJob:
    job_id: str
    type: NsqdJobType
    status: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime | None


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class CorpusRecordStore(Protocol):
    def put(self, record: dict[str, Any]) -> None: ...

    def get(self, record_id: str) -> dict[str, Any] | None: ...

    def list_ids(self) -> list[str]: ...


@runtime_checkable
class CorpusSnapshotStore(Protocol):
    def commit(self, snapshot_id: str, record_ids: list[str], schema_version: int) -> None: ...

    def get(self, snapshot_id: str) -> dict[str, Any] | None: ...

    def record_ids(self, snapshot_id: str) -> list[str]: ...


@runtime_checkable
class CorpusIndex(Protocol):
    def upsert(self, snapshot_id: str, record_id: str, vector: list[float]) -> None: ...

    def query(self, snapshot_id: str, vector: list[float], k: int) -> list[CorpusHit]: ...


@runtime_checkable
class MorphospaceStore(Protocol):
    def mark_inspected(self, cell_id: str, inspected_at: datetime) -> None: ...

    def get_cell(self, cell_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class NsqdCandidateStore(Protocol):
    def put_artifact(self, artifact_hash: str, payload: dict[str, Any]) -> None: ...

    def get_artifact(self, artifact_hash: str) -> dict[str, Any] | None: ...


@runtime_checkable
class FrontierCardStore(Protocol):
    def put_card(self, card: dict[str, Any]) -> None: ...

    def get_card(self, card_id: str) -> dict[str, Any] | None: ...

    def elite_for_cell(self, cell_id: str) -> dict[str, Any] | None: ...

    def set_elite(self, cell_id: str, card_id: str | None) -> None: ...


@runtime_checkable
class NsqdJobQueue(Protocol):
    def enqueue(
        self,
        type: NsqdJobType,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str: ...

    def claim_next(self, now: datetime) -> NsqdJob | None: ...

    def mark_succeeded(self, job_id: str) -> None: ...

    def mark_retryable(self, job_id: str, error: str, run_after: datetime) -> None: ...

    def mark_failed(self, job_id: str, error: str) -> None: ...

    def cancel(self, job_id: str) -> None: ...
