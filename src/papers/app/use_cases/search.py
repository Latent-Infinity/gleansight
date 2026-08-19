"""Search use-cases for finding and filtering papers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from papers.app import ports


class PapersFTS(Protocol):
    """Protocol for full-text search."""

    def search(self, query: str, limit: int) -> list[str]: ...


class VectorIndex(Protocol):
    """Protocol for vector index."""

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]: ...


class Embedder(Protocol):
    """Protocol for embedder."""

    def embed(self, text: str) -> list[float]: ...


class ExtractionStore(Protocol):
    """Protocol for extraction store."""

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict[str, Any],
        latest_only: bool = True,
    ) -> list[str]: ...


def compute_rrf_scores(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Compute Reciprocal Rank Fusion scores.

    Args:
        rankings: List of ranked paper ID lists
        k: RRF constant (default 60 per design doc)

    Returns:
        Dict mapping paper_id to RRF score
    """
    scores: dict[str, float] = {}

    for ranking in rankings:
        for rank, paper_id in enumerate(ranking, start=1):
            score = 1.0 / (k + rank)
            scores[paper_id] = scores.get(paper_id, 0.0) + score

    return scores


@dataclass(frozen=True)
class SearchPapersUseCase:
    """Search papers using hybrid FTS + vector search with RRF fusion."""

    papers_fts: PapersFTS
    vector_index: VectorIndex
    embedder: Embedder

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search for papers using hybrid search.

        Combines FTS and vector search results using Reciprocal Rank Fusion (RRF).

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of results with paper_id and score, sorted by RRF score
        """
        if not query or not query.strip():
            return []

        # Fetch more results from each source for better fusion
        fetch_limit = min(limit * 3, 100)

        # Execute FTS search
        fts_results = self.papers_fts.search(query, limit=fetch_limit)

        # Execute vector search
        embedding = self.embedder.embed(query)
        vector_results = self.vector_index.query(embedding, limit=fetch_limit)
        vector_paper_ids = [paper_id for paper_id, _ in vector_results]

        # Combine using RRF
        rankings = []
        if fts_results:
            rankings.append(fts_results)
        if vector_paper_ids:
            rankings.append(vector_paper_ids)

        if not rankings:
            return []

        # Compute RRF scores
        rrf_scores = compute_rrf_scores(rankings, k=60)

        # Sort by score and return top N
        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return [
            {"paper_id": paper_id, "score": score} for paper_id, score in sorted_results[:limit]
        ]


@dataclass(frozen=True)
class FilterByExtractionsUseCase:
    """Filter papers by extracted field values."""

    extraction_store: ExtractionStore

    def filter(
        self,
        field_path: str,
        prompt_version_id: str,
        constraints: dict[str, Any],
        latest_only: bool = True,
    ) -> list[str]:
        """Filter papers by extraction constraints.

        Args:
            field_path: Field path to filter on (e.g., "algorithm_family")
            prompt_version_id: Prompt version to scope query to
            constraints: Dict of constraints (e.g., {"value_text": "transformer"})
            latest_only: Only include extractions from latest successful runs (default: True)

        Returns:
            List of matching paper IDs
        """
        return self.extraction_store.query(
            field_path=field_path,
            prompt_version_id=prompt_version_id,
            constraints=constraints,
            latest_only=latest_only,
        )


@dataclass(frozen=True)
class AggregateExtractionsUseCase:
    """Aggregate extractions for meta-analysis."""

    extraction_store: ports.ExtractionStore

    def count_by_value(
        self,
        field_path: str,
        prompt_version_id: str,
        latest_only: bool = True,
    ) -> dict[str, int]:
        """Count papers by field value.

        Args:
            field_path: Field path to aggregate on
            prompt_version_id: Prompt version to scope query to
            latest_only: Only include extractions from latest successful runs (default: True)

        Returns:
            Dict mapping field values to counts
        """
        return self.extraction_store.count_by_value(
            field_path=field_path,
            prompt_version_id=prompt_version_id,
            latest_only=latest_only,
        )

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ) -> float | dict[str, float] | None:
        """Average numeric field value, optionally grouped.

        Args:
            field_path: Field path to average
            prompt_version_id: Prompt version to scope query to
            group_by: Optional field to group by
            latest_only: Only include extractions from latest successful runs (default: True)

        Returns:
            Average value, or dict of averages if grouped, or None if no data
        """
        return self.extraction_store.average_numeric(
            field_path=field_path,
            prompt_version_id=prompt_version_id,
            group_by=group_by,
            latest_only=latest_only,
        )
