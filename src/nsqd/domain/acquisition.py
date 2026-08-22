from __future__ import annotations

from typing import Any

from nsqd.domain.snapshot import canonical_json, sha256_hex
from nsqd.domain.sufficiency import (
    INTEGRITY_FAILURES,
    SEARCHABLE_FAILURES,
    SufficiencyFailure,
)

QUERY_BATCH_LIMIT = 3
CANDIDATES_PER_BATCH = 25
STAGED_IMPORT_LIMIT = 3
RECHECK_CYCLE_LIMIT = 2


def acquisition_route(failures: tuple[SufficiencyFailure, ...] | list[str]) -> str:
    codes = set(failures)
    if codes & INTEGRITY_FAILURES:
        return "manual"
    if codes & SEARCHABLE_FAILURES:
        return "search"
    return "stop"


def render_acquisition_query(
    *,
    policy_id: str,
    failure: str,
    cell_id: str | None = None,
    probe_id: str | None = None,
    record_type: str | None = None,
) -> str:
    parts = [policy_id, failure]
    if cell_id:
        parts.append(cell_id)
    if probe_id:
        parts.append(probe_id)
    if record_type:
        parts.append(record_type)
    return " ".join(parts)


def acquisition_cycle_id(
    *,
    snapshot_id: str,
    domain_policy_id: str,
    failure_signature: tuple[str, ...] | list[str],
    rendered_query: str,
    filters: dict[str, Any],
) -> str:
    return sha256_hex(
        canonical_json(
            {
                "snapshot_id": snapshot_id,
                "domain_policy_id": domain_policy_id,
                "failure_signature": list(failure_signature),
                "filters": filters,
                "rendered_query": rendered_query,
            }
        )
    )
