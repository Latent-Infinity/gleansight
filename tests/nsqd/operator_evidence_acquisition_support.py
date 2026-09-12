from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from nsqd.domain.acquisition import CANDIDATES_PER_BATCH
from papers.infra.blobs_fs.store import FileSystemBlobStore


def tree_manifest(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def candidate(stable_source_id: str, version: str) -> dict[str, Any]:
    content = f"{stable_source_id}:{version}".encode()
    return {
        "candidate_id": f"candidate-{stable_source_id}-{version}",
        "source_class": "test_external_catalog",
        "stable_source_id": stable_source_id,
        "source_paper_id": stable_source_id,
        "version_id": version,
        "retrieval_uri": f"test://catalog/{stable_source_id}/{version}",
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "title": f"{stable_source_id} {version}",
    }


def candidate_batches() -> tuple[tuple[dict[str, Any], ...], ...]:
    first = tuple(candidate(f"work-{index:02d}", "v1") for index in range(CANDIDATES_PER_BATCH))
    second = tuple(
        candidate(f"work-{index:02d}", "v2") for index in range(CANDIDATES_PER_BATCH - 1)
    ) + (candidate("work-25", "v1"),)
    third = tuple(
        candidate(f"work-{index:02d}", "v3") for index in range(CANDIDATES_PER_BATCH - 2)
    ) + (
        candidate("work-24", "v2"),
        candidate("work-26", "v1"),
    )
    fourth = tuple(candidate(f"work-{index:02d}", "v4") for index in range(25))
    return first, second, third, fourth


class RecordingExternalAdapter:
    def __init__(self, blob_store: FileSystemBlobStore) -> None:
        self.blob_store = blob_store
        self.pages = candidate_batches()
        self.discover_calls = 0
        self.discovered_batch_sizes: list[int] = []
        self.shortlist_candidate_counts: list[int] = []
        self.shortlist_limits: list[int] = []
        self.staged_source_ids: list[str] = []
        self.analyzed: list[str] = []

    def discover(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        page = self.pages[self.discover_calls]
        self.discover_calls += 1
        self.discovered_batch_sizes.append(len(page))
        return [dict(row) for row in page]

    def shortlist(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
        insufficiency_query: str,
        filters: dict[str, Any],
        failure_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.shortlist_candidate_counts.append(len(candidates))
        self.shortlist_limits.append(limit)
        return [{**candidates[0], "review_status": "pending"}] if limit else []

    def stage_import(self, item: dict[str, Any]) -> str:
        source_id = str(item["source_paper_id"])
        self.staged_source_ids.append(source_id)
        paper_id = f"research-paper-{len(self.staged_source_ids)}"
        self.blob_store.put_markdown(paper_id, f"test-only source for {source_id}")
        return paper_id

    def enqueue_analyze(self, paper_id: str) -> None:
        self.analyzed.append(paper_id)

    def draft_projection(self, paper_id: str) -> dict[str, Any]:
        return {
            "paper_id": paper_id,
            "review_status": "pending",
            "paraphrase": "test-only draft, not corpus evidence",
            "paraphrase_source": "deterministic_test_adapter",
        }
