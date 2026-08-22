from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from nsqd.app.handlers import (
    handle_diverge,
    handle_ground,
    handle_harvest,
    handle_project,
    handle_rescore,
    handle_score,
)
from nsqd.composition import NsqdContainer
from nsqd.ports import NsqdJob, NsqdJobType

_HANDLER_BY_JOB_TYPE: dict[NsqdJobType, Callable[[Any, NsqdJob], dict[str, Any]]] = {
    "harvest": handle_harvest,
    "project": handle_project,
    "diverge": handle_diverge,
    "ground": handle_ground,
    "score": handle_score,
    "rescore": handle_rescore,
}


def run_job(
    container: NsqdContainer,
    job_type: NsqdJobType,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    job_id = container.queue.enqueue(job_type, payload)
    claimed = container.queue.claim_job(job_id, now)
    if claimed is None:
        raise RuntimeError(f"failed to claim {job_type} job")
    try:
        result = dispatch_job(container, claimed)
    except Exception as exc:
        try:
            container.queue.mark_failed(job_id, str(exc)[:1000])
        except Exception as mark_exc:  # pragma: no cover - defensive note propagation
            exc.add_note(f"also failed to mark {job_type} job failed: {mark_exc}")
        raise
    container.queue.mark_succeeded(job_id)
    return result


def dispatch_job(container: NsqdContainer, job: NsqdJob) -> dict[str, Any]:
    handler = _HANDLER_BY_JOB_TYPE.get(job.type)
    if handler is None:
        raise ValueError(f"unsupported nsqd job type: {job.type}")
    return handler(container.ctx, job)
