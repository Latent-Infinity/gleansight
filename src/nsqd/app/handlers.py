from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nsqd.app.use_cases import (
    ArchiveInsertUseCase,
    DivergeUseCase,
    GroundUseCase,
    HarvestUseCase,
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
    digest = DivergeUseCase(candidates=ctx.candidates, clock=ctx.clock).run(
        candidate=payload["candidate"],
        axiom=str(payload["axiom"]),
        generator_run_id=str(payload["generator_run_id"]),
    )
    return {"status": "succeeded", "candidate_artifact_hash": digest}


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
