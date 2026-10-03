from __future__ import annotations

from gleansight.api.capabilities import operations as capability_operations
from gleansight.api.nsqd import operations as nsqd_operations
from gleansight.api.operation import RegisteredOperation
from gleansight.api.papers import operations as paper_operations
from gleansight.api.research import operations as research_operations
from gleansight.api.workers import operations as worker_operations
from gleansight.api.workspaces import operations as workspace_operations


def default_operations() -> tuple[RegisteredOperation, ...]:
    return (
        *capability_operations(),
        *paper_operations(),
        *nsqd_operations(),
        *workspace_operations(),
        *worker_operations(),
        *research_operations(),
    )
