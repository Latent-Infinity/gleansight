from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nsqd.app.use_cases import (
    ArchiveInsertUseCase,
    DivergeUseCase,
    GroundUseCase,
    HarvestUseCase,
    MapSnapshotUseCase,
    ProjectPaperUseCase,
    RescoreUseCase,
    ScoreUseCase,
)
from nsqd.ports import (
    Clock,
    CorpusIndex,
    CorpusRecordStore,
    CorpusSnapshotStore,
    FrontierCardStore,
    HarvestStore,
    MorphospaceStore,
    NsqdCandidateStore,
    NsqdJob,
    NsqdJobType,
)


@dataclass
class NsqdHandlerContext:
    clock: Clock
    candidates: NsqdCandidateStore
    cards: FrontierCardStore
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore
    harvest: HarvestStore
    index: CorpusIndex
    morph: MorphospaceStore
    approved_projection_digests: frozenset[str] = frozenset()
    scholar_client: Any = None
    paper_vector_index: Any = None


def _require_job_type(job: NsqdJob, expected_type: NsqdJobType) -> None:
    if job.type != expected_type:
        raise ValueError(f"expected job.type={expected_type}, got {job.type}")


def _require_payload_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _require_expected_cell_ids(payload: dict[str, Any]) -> frozenset[str] | None:
    if "expected_cell_ids" not in payload:
        return None
    value = payload["expected_cell_ids"]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected_cell_ids must be a list of strings")
    return frozenset(value)


def handle_harvest(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "harvest")
    result = HarvestUseCase(
        harvest=ctx.harvest,
        clock=ctx.clock,
    ).run(job.payload["payload"])
    return {"status": "succeeded", **result}


def handle_project(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "project")
    payload = job.payload
    projection = payload["projection"]
    if not isinstance(projection, dict):
        raise ValueError("projection must be a mapping")
    result = ProjectPaperUseCase(
        harvest=ctx.harvest,
        records=ctx.records,
        clock=ctx.clock,
        approved_projection_digests=ctx.approved_projection_digests,
    ).run(
        domain_policy_id=str(payload.get("domain_policy_id") or ""),
        projection=projection,
    )
    return {"status": "succeeded", **result}


def handle_diverge(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "diverge")
    payload = job.payload
    axioms = payload.get("axioms")
    if "axioms" in payload and not isinstance(axioms, list):
        raise ValueError("axioms must be a list")
    axiom = payload.get("axiom")
    parent = payload.get("parent_card_id")
    target = payload.get("target_cell_id")
    cell_statuses = payload.get("cell_statuses")
    if "cell_statuses" in payload and not isinstance(cell_statuses, dict):
        raise ValueError("cell_statuses must be a mapping")
    digest = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=payload["candidate"],
        generator_run_id=str(payload["generator_run_id"]),
        axiom=str(axiom) if axiom is not None else None,
        axioms=axioms,
        operator=str(payload.get("operator") or "A"),
        parent_card_id=str(parent) if parent is not None else None,
        target_cell_id=str(target) if target is not None else None,
        cell_statuses=cell_statuses,
    )
    return {"status": "succeeded", "candidate_artifact_hash": digest}


def handle_map(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "map")
    payload = job.payload
    result = MapSnapshotUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        morph=ctx.morph,
        clock=ctx.clock,
    ).run(
        snapshot_id=_require_payload_string(payload, "snapshot_id"),
        domain_policy_id=_require_payload_string(payload, "domain_policy_id"),
        snapshot_state=_require_payload_string(payload, "snapshot_state"),
        expected_cell_ids=_require_expected_cell_ids(payload),
    )
    return {"status": "succeeded", **result}


def handle_ground(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "ground")
    payload = job.payload
    result = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(
        candidate_artifact_hash=str(payload["candidate_artifact_hash"]),
        snapshot_id=str(payload["snapshot_id"]),
        corpus_version=int(payload["corpus_version"]),
    )
    return {"status": "succeeded", **result}


def handle_score(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "score")
    payload = job.payload
    scored = ScoreUseCase(
        candidates=ctx.candidates,
        cards=ctx.cards,
        snapshots=ctx.snapshots,
        records=ctx.records,
    ).run(
        candidate_artifact_hash=str(payload["candidate_artifact_hash"]),
        evaluator_run_id=str(payload["evaluator_run_id"]),
        snapshot_id=str(payload["snapshot_id"]),
        corpus_version=int(payload["corpus_version"]),
        snapshot_state=str(payload["snapshot_state"]),
    )
    archived = ArchiveInsertUseCase(cards=ctx.cards).run(scored["card"])
    return {
        "status": "succeeded",
        "viability": scored["viability"],
        "cell_id": scored["card"]["cell_id"],
        "card_decision": scored["card"]["card_decision"],
        "archive": archived,
    }


def handle_rescore(ctx: NsqdHandlerContext, job: NsqdJob) -> dict[str, Any]:
    _require_job_type(job, "rescore")
    payload = job.payload
    result = RescoreUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        cards=ctx.cards,
    ).run(
        card_id=str(payload["card_id"]),
        current_snapshot_id=str(payload["current_snapshot_id"]),
        current_corpus_version=int(payload["current_corpus_version"]),
        snapshot_state="smoke_only",
        evaluator_run_id=f"rescore:{job.job_id}",
    )
    return {"status": "succeeded", **result}
