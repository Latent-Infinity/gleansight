"""Public supervised worker lifecycle and persisted progress operations."""

from __future__ import annotations

from pydantic import Field, JsonValue

from gleansight.api.models import EmptyRequest, Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from gleansight.workers.models import WorkerLimits
from gleansight.workers.supervisor import WorkerSupervisor


class StartWorker(Request):
    limits: WorkerLimits = Field(default_factory=WorkerLimits)


class WorkerId(Request):
    worker_id: Identifier


def start(runtime: ApiRuntime, request: StartWorker) -> JsonValue:
    state = WorkerSupervisor(runtime.configuration).start(request.limits)
    return json_result(state.model_dump(mode="json", exclude={"configuration"}))


def status(runtime: ApiRuntime, request: WorkerId) -> JsonValue:
    return json_result(
        WorkerSupervisor(runtime.configuration)
        .status(request.worker_id)
        .model_dump(mode="json", exclude={"configuration"})
    )


def list_workers(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    return json_result(
        [
            state.model_dump(mode="json", exclude={"configuration"})
            for state in WorkerSupervisor(runtime.configuration).list()
        ]
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.workers.start",
            "Start one bounded supervised process for this workspace.",
            StartWorker,
            start,
            ("write", "external"),
        ),
        Operation(
            "papers.workers.status",
            "Read durable progress and pending checkpoint controls.",
            WorkerId,
            status,
        ),
        Operation(
            "papers.workers.list",
            "List supervised worker runs in this workspace.",
            EmptyRequest,
            list_workers,
        ),
        *tuple(
            Operation(
                f"papers.workers.{name}",
                description,
                WorkerId,
                lambda runtime, request, desired=desired: json_result(
                    WorkerSupervisor(runtime.configuration)
                    .control(request.worker_id, desired)
                    .model_dump(mode="json", exclude={"configuration"})
                ),
                ("write",),
            )
            for name, desired, description in (
                ("pause", "pause", "Pause intake at the next job boundary; active calls continue."),
                ("resume", "run", "Resume intake within the original resource limits."),
                ("stop", "stop", "Stop at the next job boundary; active calls continue."),
            )
        ),
    )
