from gleansight.api.operation import RegisteredOperation
from gleansight.api.papers import (
    candidates,
    indexes,
    jobs,
    pipeline,
    profiles,
    prompts,
    query,
    records,
    research,
    taxonomy,
)


def operations() -> tuple[RegisteredOperation, ...]:
    """Return the paper application's typed local operations."""
    return (
        *candidates.operations(),
        *records.operations(),
        *pipeline.operations(),
        *jobs.operations(),
        *prompts.operations(),
        *taxonomy.operations(),
        *query.operations(),
        *profiles.operations(),
        *research.operations(),
        *indexes.operations(),
    )
