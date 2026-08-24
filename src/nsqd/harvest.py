from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.composition import build_container, fixed_clock
from nsqd.ports import ParaphraseEmbedder
from nsqd.runner import run_job

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
    embedder: ParaphraseEmbedder,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    clock = fixed_clock(as_of) if as_of is not None else None
    container = build_container(
        db_path=db_path,
        index_path=index_path,
        clock=clock,
        embedder=embedder,
    )
    payload = parse_harvest_file(file_path)
    return run_job(
        container,
        "harvest",
        {"filename": str(file_path), "payload": payload},
        container.clock.now(),
    )
