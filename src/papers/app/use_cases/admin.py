from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from papers.app import ports


@dataclass(frozen=True)
class RecoverStuckJobsUseCase:
    job_queue: ports.JobQueue
    stuck_after: timedelta = timedelta(hours=1)

    def __call__(self, *, now: datetime | None = None) -> list[str]:
        if now is None:
            now = datetime.now(UTC)
        cutoff = now - self.stuck_after
        return self.job_queue.requeue_running_before(cutoff, "stuck job recovered")


@dataclass(frozen=True)
class RebuildVectorIndexUseCase:
    paper_store: ports.PaperStore
    blob_store: ports.BlobStore
    embedder: ports.Embedder
    vector_index: ports.VectorIndex

    def __call__(self) -> int:
        paper_ids = self.paper_store.list_papers_with_markdown()
        self.vector_index.reset()
        processed = 0
        for paper_id in paper_ids:
            path = self.blob_store.get_markdown_path(paper_id)
            if path is None:
                continue
            text = path.read_text(encoding="utf-8")
            embedding = self.embedder.embed(text)
            self.vector_index.upsert(paper_id, embedding)
            processed += 1
        return processed


@dataclass(frozen=True)
class RebuildTitleAbstractIndexUseCase:
    rebuild: Callable[[], int]

    def __call__(self) -> int:
        return self.rebuild()
