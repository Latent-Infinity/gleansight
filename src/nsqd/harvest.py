from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.app.handlers import handle_harvest
from nsqd.composition import build_container, fixed_clock

MAX_HARVEST_FILE_BYTES = 10 * 1024 * 1024


def parse_harvest_file(path: Path) -> Any:
    if path.stat().st_size > MAX_HARVEST_FILE_BYTES:
        raise ValueError("harvest file is too large")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return text
    if suffix == ".toml":
        return tomllib.loads(text)
    loaded = yaml.safe_load(text)
    return text if loaded is None else loaded


def run_harvest(
    *,
    file_path: Path,
    db_path: Path,
    index_path: Path,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    clock = fixed_clock(as_of) if as_of is not None else None
    container = build_container(db_path=db_path, index_path=index_path, clock=clock)
    payload = parse_harvest_file(file_path)
    now = container.clock.now()
    job_id = container.queue.enqueue(
        "harvest",
        {"filename": str(file_path), "payload": payload},
    )
    claimed = container.queue.claim_job(job_id, now)
    if claimed is None:
        raise RuntimeError("failed to claim harvest job")
    try:
        result = handle_harvest(container.ctx, claimed)
    except Exception as exc:
        try:
            container.queue.mark_failed(job_id, str(exc)[:1000])
        except Exception as mark_exc:
            exc.add_note(f"also failed to mark harvest job failed: {mark_exc}")
        raise
    container.queue.mark_succeeded(job_id)
    return result
