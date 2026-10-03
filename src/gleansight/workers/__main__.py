"""Internal worker subprocess entry point; the public supervisor owns lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from gleansight.workers.runner import run_worker
from gleansight.workers.store import WorkerStore


def main(
    database: Annotated[Path, typer.Option()],
    worker_id: Annotated[str, typer.Option()],
    lock_fd: Annotated[int, typer.Option()],
) -> None:
    with os.fdopen(lock_fd, "rb"):
        run_worker(WorkerStore(database), worker_id)


if __name__ == "__main__":
    typer.run(main)
