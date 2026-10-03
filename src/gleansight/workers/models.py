"""Persisted worker controls, resource bounds, and truthful progress."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from gleansight.api.runtime import ApiConfiguration

type DesiredState = Literal["run", "pause", "stop"]
type WorkerPhase = Literal[
    "starting", "running", "paused", "stopping", "stopped", "failed", "interrupted"
]


class WorkerLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_cycles: Annotated[int, Field(ge=1, le=100000)] = 1000
    max_jobs: Annotated[int, Field(ge=1, le=10000)] = 100
    max_seconds: Annotated[float, Field(gt=0, le=86400)] = 300
    max_tokens: Annotated[int, Field(ge=0)] | None = None
    poll_interval: Annotated[float, Field(ge=0.05, le=10)] = 0.25
    concurrency: Literal[1] = 1


class WorkerState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    worker_id: str
    phase: WorkerPhase = "starting"
    desired_state: DesiredState = "run"
    configuration: ApiConfiguration
    limits: WorkerLimits
    created_at: str
    heartbeat_at: str
    pid: int | None = None
    active_job_id: str | None = None
    active_run_id: str | None = None
    cycles: int = 0
    jobs_processed: int = 0
    tokens_used: int | None = 0
    stop_reason: str | None = None
    error: str | None = None
    log_path: str
    checkpoint_policy: str = (
        "Pause, stop, and elapsed-time limits stop intake at job boundaries; "
        "active provider calls are not interrupted."
    )
