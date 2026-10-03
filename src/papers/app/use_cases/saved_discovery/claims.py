"""Use ordinary running jobs to coordinate on-demand discovery with backups and workers."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import JsonValue, TypeAdapter

from papers.domain.errors import ConflictError
from papers.infra.screening import ScreeningStore


@contextmanager
def discovery_claim(
    store: ScreeningStore, search_id: str, run_id: str, *, managed: bool
) -> Iterator[None]:
    with store.transaction() as connection:
        existing = connection.execute(
            "SELECT status, payload_json FROM jobs WHERE job_id = ?", (run_id,)
        ).fetchone()
        if managed:
            if (
                existing is None
                or existing[0] != "running"
                or TypeAdapter(dict[str, JsonValue])
                .validate_json(existing[1])
                .get("saved_search_id")
                != search_id
            ):
                raise ConflictError("Managed discovery requires its claimed running job.")
        else:
            if existing is not None:
                raise ConflictError("Discovery run identifier is already claimed by a job.")
            now = datetime.now(UTC).isoformat()
            connection.execute(
                "INSERT INTO jobs(job_id,type,status,paper_id,run_id,payload_json,"
                "attempts,max_attempts,"
                "run_after,created_at,updated_at) VALUES (?, "
                "'discover','running',NULL,NULL,?,1,1,NULL,?,?)",
                (run_id, json.dumps({"saved_search_id": search_id}), now, now),
            )
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        if not managed:
            with store.transaction() as connection:
                connection.execute(
                    "UPDATE jobs SET status=?, updated_at=? WHERE job_id=?",
                    ("succeeded" if succeeded else "failed", datetime.now(UTC).isoformat(), run_id),
                )
