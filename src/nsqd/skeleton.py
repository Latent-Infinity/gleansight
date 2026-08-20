from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.app.handlers import handle_diverge, handle_ground, handle_score
from nsqd.app.use_cases import empty_smoke_snapshot_id
from nsqd.composition import NsqdContainer, build_container, fixed_clock
from nsqd.domain.status import cell_status
from nsqd.ports import NsqdJob, NsqdJobType


def run_skeleton(
    *,
    fixture_path: Path,
    axiom: str,
    db_path: Path,
    index_path: Path,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    clock = fixed_clock(as_of) if as_of is not None else None
    container = build_container(db_path=db_path, index_path=index_path, clock=clock)
    payload = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("candidate fixture must be a mapping")
    snapshot = empty_smoke_snapshot_id()
    container.ctx.snapshots.commit(snapshot, [], schema_version=1)
    generator_run_id = str(uuid.uuid4())
    evaluator_run_id = str(uuid.uuid4())
    now = container.clock.now()

    diverge = _run_job(
        container,
        "diverge",
        {
            "candidate": payload,
            "axiom": axiom,
            "generator_run_id": generator_run_id,
        },
        now,
    )
    artifact_hash = str(diverge["candidate_artifact_hash"])
    grounding = _run_job(
        container,
        "ground",
        {
            "candidate_artifact_hash": artifact_hash,
            "snapshot_id": snapshot,
            "corpus_version": 1,
        },
        now,
    )
    scored = _run_job(
        container,
        "score",
        {
            "candidate_artifact_hash": artifact_hash,
            "snapshot_id": snapshot,
            "corpus_version": 1,
            "evaluator_run_id": evaluator_run_id,
            "snapshot_state": "smoke_only",
        },
        now,
    )
    artifact = container.ctx.candidates.get_artifact(artifact_hash)
    assert artifact is not None
    card = container.ctx.cards.get_card(artifact_hash)
    assert card is not None
    elite = container.ctx.cards.elite_for_cell(str(card["cell_id"]))
    archive_empty = (
        container.database.fetchone("SELECT 1 AS has_elite FROM nsqd_elites LIMIT 1") is None
    )
    status = cell_status(
        [],
        as_of=now,
        snapshot_state="smoke_only",
        inspected=True,
        expected=True,
    )
    job_rows = container.database.fetchall("SELECT type, status FROM nsqd_jobs")
    return {
        "snapshot_id": snapshot,
        "snapshot_empty": container.ctx.snapshots.record_ids(snapshot) == [],
        "candidate_artifact_hash": artifact_hash,
        "evidence": artifact.get("novelty", {}).get("evidence", grounding.get("evidence")),
        "nov": card["nov"],
        "viability": scored["viability"],
        "card": card,
        "archive": scored["archive"],
        "elite": elite,
        "archive_empty": archive_empty,
        "cell_status": status,
        "grounding": artifact.get("grounding", grounding),
        "novelty": artifact.get("novelty"),
        "job_types": {str(row["type"]) for row in job_rows if row["status"] == "succeeded"},
        "expected_outcomes": payload.get("expected_outcomes") or {},
        "generator_run_id": generator_run_id,
        "evaluator_run_id": evaluator_run_id,
    }


def _run_job(
    container: NsqdContainer,
    job_type: NsqdJobType,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    job_id = container.queue.enqueue(job_type, payload)
    claimed = container.queue.claim_job(job_id, now)
    if claimed is None:
        raise RuntimeError(f"failed to claim {job_type} job")
    result = _dispatch(container, claimed)
    container.queue.mark_succeeded(job_id)
    return result


def _dispatch(container: NsqdContainer, job: NsqdJob) -> dict[str, Any]:
    if job.type == "diverge":
        return handle_diverge(container.ctx, job)
    if job.type == "ground":
        return handle_ground(container.ctx, job)
    if job.type == "score":
        return handle_score(container.ctx, job)
    raise ValueError(f"unsupported skeleton job type: {job.type}")
