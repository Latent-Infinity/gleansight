from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from papers.app.use_cases.admin import RebuildVectorIndexUseCase, RecoverStuckJobsUseCase


@dataclass
class FakeJobQueue:
    recovered: list[tuple[datetime, str]] = field(default_factory=list)

    def requeue_running_before(self, cutoff: datetime, error: str) -> list[str]:
        self.recovered.append((cutoff, error))
        return ["job-1", "job-2"]


@dataclass
class FakePaperStore:
    paper_ids: list[str]

    def list_papers_with_markdown(self) -> list[str]:
        return list(self.paper_ids)


@dataclass
class FakeBlobStore:
    markdowns: dict[str, Path]

    def get_markdown_path(self, paper_id: str) -> Path | None:
        return self.markdowns.get(paper_id)


@dataclass
class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [float(len(text))]


@dataclass
class FakeVectorIndex:
    reset_calls: int = 0
    upserts: list[tuple[str, list[float]]] = field(default_factory=list)

    def reset(self) -> None:
        self.reset_calls += 1

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        self.upserts.append((paper_id, embedding))


def test_recover_stuck_jobs_requeues() -> None:
    queue = FakeJobQueue()
    use_case = RecoverStuckJobsUseCase(job_queue=queue, stuck_after=timedelta(hours=2))
    now = datetime(2024, 1, 1, tzinfo=UTC)

    recovered = use_case(now=now)

    assert recovered == ["job-1", "job-2"]
    cutoff, error = queue.recovered[0]
    assert cutoff == now - timedelta(hours=2)
    assert error == "stuck job recovered"


def test_recover_stuck_jobs_defaults_to_now() -> None:
    queue = FakeJobQueue()
    use_case = RecoverStuckJobsUseCase(job_queue=queue, stuck_after=timedelta(hours=1))

    recovered = use_case()

    assert recovered == ["job-1", "job-2"]
    cutoff, _ = queue.recovered[0]
    assert isinstance(cutoff, datetime)


def test_rebuild_vector_index_reembeds(tmp_path: Path) -> None:
    paper_store = FakePaperStore(["paper-1", "paper-2"])
    markdown_path = tmp_path / "paper.md"
    markdown_path.write_text("hello", encoding="utf-8")
    blob_store = FakeBlobStore({"paper-1": markdown_path, "paper-2": markdown_path})
    embedder = FakeEmbedder()
    vector_index = FakeVectorIndex()

    use_case = RebuildVectorIndexUseCase(
        paper_store=paper_store,
        blob_store=blob_store,
        embedder=embedder,
        vector_index=vector_index,
    )

    count = use_case()

    assert count == 2
    assert vector_index.reset_calls == 1
    assert vector_index.upserts[0][0] == "paper-1"
    assert vector_index.upserts[1][0] == "paper-2"


def test_rebuild_vector_index_skips_missing_markdown(tmp_path: Path) -> None:
    paper_store = FakePaperStore(["paper-1", "paper-2"])
    markdown_path = tmp_path / "paper.md"
    markdown_path.write_text("hello", encoding="utf-8")
    blob_store = FakeBlobStore({"paper-1": markdown_path})
    embedder = FakeEmbedder()
    vector_index = FakeVectorIndex()

    use_case = RebuildVectorIndexUseCase(
        paper_store=paper_store,
        blob_store=blob_store,
        embedder=embedder,
        vector_index=vector_index,
    )

    count = use_case()

    assert count == 1
    assert vector_index.upserts == [("paper-1", [5.0])]
