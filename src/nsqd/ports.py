from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class CorpusHit:
    record_id: str
    distance: float
    rank: int


@dataclass(frozen=True)
class HarvestCommit:
    record_ids: tuple[str, ...]
    snapshot_id: str
    corpus_version: int


NsqdJobType = Literal[
    "harvest", "project", "diverge", "ground", "score", "rescore", "map", "acquire"
]
NSQD_JOB_TYPES: frozenset[str] = frozenset(
    {"harvest", "project", "diverge", "ground", "score", "rescore", "map", "acquire"}
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
    def commit(self, snapshot_id: str, record_ids: list[str], schema_version: int) -> int: ...

    def get(self, snapshot_id: str) -> dict[str, Any] | None: ...

    def record_ids(self, snapshot_id: str) -> list[str]: ...


@runtime_checkable
class HarvestStore(Protocol):
    def commit(self, records: list[dict[str, Any]], schema_version: int) -> HarvestCommit: ...


@runtime_checkable
class ParaphraseEmbedder(Protocol):
    def model_id(self) -> str: ...

    def model_version(self) -> str: ...

    def dimension(self) -> int: ...

    def normalization_policy(self) -> str: ...

    def embed(self, text: str) -> list[float]: ...


@runtime_checkable
class CorpusIndex(Protocol):
    def upsert(self, snapshot_id: str, record_id: str, vector: list[float]) -> None: ...

    def query(
        self,
        snapshot_id: str,
        vector: list[float],
        k: int,
        *,
        allowed_record_ids: frozenset[str] | None = None,
    ) -> list[CorpusHit]: ...


@runtime_checkable
class HybridPaperSearch(Protocol):
    """Read-only N5 prior-art search; acquisition remains paper-owned in N6."""

    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...


@runtime_checkable
class LivePaperSearch(Protocol):
    """Read-only N5 scholar search; it does not import or approve evidence."""

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class MorphospaceStore(Protocol):
    def mark_inspected(self, cell_id: str, inspected_at: datetime) -> None: ...

    def get_cell(self, cell_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class NsqdCandidateStore(Protocol):
    def put_artifact_if_absent(self, artifact_hash: str, payload: dict[str, Any]) -> bool: ...

    def put_artifact(self, artifact_hash: str, payload: dict[str, Any]) -> None: ...

    def get_artifact(self, artifact_hash: str) -> dict[str, Any] | None: ...


@runtime_checkable
class FrontierCardStore(Protocol):
    def put_card(self, card: dict[str, Any]) -> None: ...

    def get_card(self, card_id: str) -> dict[str, Any] | None: ...

    def elite_for_cell(self, cell_id: str) -> dict[str, Any] | None: ...

    def set_elite(self, cell_id: str, card_id: str | None) -> None: ...

    def list_elites(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class NsqdJobQueue(Protocol):
    def enqueue(
        self,
        type: NsqdJobType,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str: ...

    def claim_next(self, now: datetime) -> NsqdJob | None: ...

    def claim_job(self, job_id: str, now: datetime) -> NsqdJob | None: ...

    def mark_succeeded(self, job_id: str) -> None: ...

    def mark_retryable(self, job_id: str, error: str, run_after: datetime) -> None: ...

    def mark_failed(self, job_id: str, error: str) -> None: ...

    def cancel(self, job_id: str) -> None: ...


@runtime_checkable
class PolicyVerdictStore(Protocol):
    def put_verdict(
        self, *, snapshot_id: str, domain_policy_id: str, verdict: dict[str, Any]
    ) -> None: ...

    def get_verdict(self, *, snapshot_id: str, domain_policy_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class AcquisitionCycleStore(Protocol):
    def put_cycle(self, cycle_id: str, payload: dict[str, Any]) -> None: ...

    def get(self, cycle_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class ApprovedDigestStore(Protocol):
    def add(self, digest: str, *, approved_at: datetime) -> None: ...

    def list_digests(self) -> frozenset[str]: ...


@runtime_checkable
class PaperAcquisitionBridge(Protocol):
    def discover(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]: ...

    def shortlist(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
        insufficiency_query: str,
        filters: dict[str, Any],
        failure_context: dict[str, Any],
    ) -> list[dict[str, Any]]: ...

    def stage_import(self, candidate: dict[str, Any]) -> str: ...

    def enqueue_analyze(self, paper_id: str) -> None: ...

    def draft_projection(self, paper_id: str) -> dict[str, Any]: ...
