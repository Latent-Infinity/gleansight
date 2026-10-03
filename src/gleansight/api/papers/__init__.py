from gleansight.api.operation import RegisteredOperation
from gleansight.api.papers import (
    candidates,
    comparisons,
    exports,
    grounding,
    indexes,
    jobs,
    pipeline,
    profiles,
    prompts,
    query,
    records,
    research,
    reviews,
    screening,
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
        *exports.operations(),
        *comparisons.operations(),
        *grounding.operations(),
        *reviews.operations(),
        *screening.operations(),
    )
