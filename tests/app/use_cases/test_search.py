from __future__ import annotations

from typing import Any

import pytest

from papers.app.use_cases.search import (
    AggregateExtractionsUseCase,
    FilterByExtractionsUseCase,
    SearchPapersUseCase,
    compute_rrf_scores,
)


class FakePapersFTS:
    """Fake FTS for testing."""

    def __init__(self, results: list[str] | None = None) -> None:
        self.results = results or []

    def search(self, query: str, limit: int) -> list[str]:
        """Return paper IDs matching query."""
        return self.results[:limit]


class FakeVectorIndex:
    """Fake vector index for testing."""

    def __init__(self, results: list[tuple[str, float]] | None = None) -> None:
        self.results = results or []

    def query(self, embedding: list[float], limit: int) -> list[tuple[str, float]]:
        """Return paper IDs with similarity scores."""
        return self.results[:limit]


class FakeEmbedder:
    """Fake embedder for testing."""

    def embed(self, text: str) -> list[float]:
        """Return dummy embedding."""
        return [0.1] * 384


class FakeExtractionStore:
    """Fake extraction store for testing."""

    def __init__(self) -> None:
        self.extractions: dict[str, list[str]] = {}
        self.counts: dict[str, dict[str, int]] = {}
        self.averages: dict[str, float | dict[str, float] | None] = {}

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict[str, Any],
        latest_only: bool = True,
    ) -> list[str]:
        """Return paper IDs matching constraints."""
        # Simplified fake - just return stored results
        key = f"{field_path}:{prompt_version_id}:{str(constraints)}"
        return self.extractions.get(key, [])

    def set_query_result(
        self,
        field_path: str,
        prompt_version_id: str,
        constraints: dict[str, Any],
        paper_ids: list[str],
    ) -> None:
        """Set expected query result for testing."""
        key = f"{field_path}:{prompt_version_id}:{str(constraints)}"
        self.extractions[key] = paper_ids

    def count_by_value(
        self,
        field_path: str,
        prompt_version_id: str,
        latest_only: bool = True,
    ) -> dict[str, int]:
        """Return counts by value."""
        key = f"{field_path}:{prompt_version_id}"
        return self.counts.get(key, {})

    def set_count_result(
        self,
        field_path: str,
        prompt_version_id: str,
        counts: dict[str, int],
    ) -> None:
        """Set expected count result for testing."""
        key = f"{field_path}:{prompt_version_id}"
        self.counts[key] = counts

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ) -> float | dict[str, float] | None:
        """Return average numeric value."""
        if group_by:
            key = f"{field_path}:{prompt_version_id}:{group_by}"
        else:
            key = f"{field_path}:{prompt_version_id}"
        return self.averages.get(key)

    def set_average_result(
        self,
        field_path: str,
        prompt_version_id: str,
        average: float | dict[str, float] | None,
        group_by: str | None = None,
    ) -> None:
        """Set expected average result for testing."""
        if group_by:
            key = f"{field_path}:{prompt_version_id}:{group_by}"
        else:
            key = f"{field_path}:{prompt_version_id}"
        self.averages[key] = average


class FakeAnalysisRunStore:
    """Fake analysis run store for testing."""

    def __init__(self) -> None:
        self.runs: dict[tuple[str, str], dict[str, Any]] = {}

    def get_latest_successful_run(
        self,
        *,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> dict[str, Any] | None:
        """Return latest successful run."""
        key = (paper_id, prompt_version_id)
        return self.runs.get(key)

    def set_run(
        self,
        paper_id: str,
        prompt_version_id: str,
        run_data: dict[str, Any],
    ) -> None:
        """Set run data for testing."""
        key = (paper_id, prompt_version_id)
        self.runs[key] = run_data


class TestComputeRRFScores:
    """Test RRF score computation."""

    def test_rrf_with_single_list(self) -> None:
        """RRF with single list should rank by position."""
        rankings = [["p1", "p2", "p3"]]
        scores = compute_rrf_scores(rankings, k=60)

        # Scores: p1=1/(60+0), p2=1/(60+1), p3=1/(60+2)
        assert scores["p1"] == pytest.approx(1 / 60)
        assert scores["p2"] == pytest.approx(1 / 61)
        assert scores["p3"] == pytest.approx(1 / 62)

    def test_rrf_with_multiple_lists_overlapping(self) -> None:
        """RRF should combine scores from multiple lists."""
        # p1 appears in both lists at rank 0 and 1
        # p2 appears only in first list at rank 1
        # p3 appears only in second list at rank 0
        rankings = [
            ["p1", "p2"],
            ["p3", "p1"],
        ]
        scores = compute_rrf_scores(rankings, k=60)

        # p1: 1/60 + 1/61 = 0.0333...
        # p2: 1/61 = 0.0163...
        # p3: 1/60 = 0.0166...
        assert scores["p1"] > scores["p3"]
        assert scores["p3"] > scores["p2"]

    def test_rrf_with_k_60(self) -> None:
        """RRF should use k=60 as specified in design doc."""
        rankings = [["p1"]]
        scores = compute_rrf_scores(rankings, k=60)
        assert scores["p1"] == pytest.approx(1 / 60)

    def test_rrf_with_empty_lists(self) -> None:
        """RRF with empty lists should return empty dict."""
        scores = compute_rrf_scores([], k=60)
        assert scores == {}

    def test_rrf_with_no_overlap(self) -> None:
        """RRF should handle non-overlapping lists."""
        rankings = [["p1", "p2"], ["p3", "p4"]]
        scores = compute_rrf_scores(rankings, k=60)

        assert len(scores) == 4
        # All from rank 0 or 1 in their respective lists
        assert scores["p1"] == pytest.approx(1 / 60)
        assert scores["p2"] == pytest.approx(1 / 61)
        assert scores["p3"] == pytest.approx(1 / 60)
        assert scores["p4"] == pytest.approx(1 / 61)


class TestSearchPapersUseCase:
    """Test SearchPapersUseCase with hybrid search."""

    def test_search_fts_only(self) -> None:
        """Should perform FTS search when query provided."""
        fts = FakePapersFTS(results=["p1", "p2", "p3"])
        vector_index = FakeVectorIndex(results=[])
        embedder = FakeEmbedder()

        use_case = SearchPapersUseCase(
            papers_fts=fts,
            vector_index=vector_index,
            embedder=embedder,
        )

        results = use_case.search(query="deep learning", limit=10)

        assert len(results) == 3
        assert results[0]["paper_id"] == "p1"
        assert results[1]["paper_id"] == "p2"
        assert results[2]["paper_id"] == "p3"
        # Scores should be present
        assert all("score" in r for r in results)

    def test_search_vector_only(self) -> None:
        """Should perform vector search when query provided."""
        fts = FakePapersFTS(results=[])
        vector_index = FakeVectorIndex(results=[("p1", 0.9), ("p2", 0.8), ("p3", 0.7)])
        embedder = FakeEmbedder()

        use_case = SearchPapersUseCase(
            papers_fts=fts,
            vector_index=vector_index,
            embedder=embedder,
        )

        results = use_case.search(query="neural networks", limit=10)

        assert len(results) == 3
        assert results[0]["paper_id"] == "p1"
        assert results[1]["paper_id"] == "p2"
        assert results[2]["paper_id"] == "p3"

    def test_search_hybrid_with_rrf_fusion(self) -> None:
        """Should fuse FTS and vector results using RRF."""
        # FTS returns: p1, p2, p3
        # Vector returns: p3, p4, p5
        # p3 appears in both, so should rank highest
        fts = FakePapersFTS(results=["p1", "p2", "p3"])
        vector_index = FakeVectorIndex(results=[("p3", 0.95), ("p4", 0.9), ("p5", 0.85)])
        embedder = FakeEmbedder()

        use_case = SearchPapersUseCase(
            papers_fts=fts,
            vector_index=vector_index,
            embedder=embedder,
        )

        results = use_case.search(query="machine learning", limit=10)

        # p3 should be first (appears in both lists)
        assert len(results) == 5
        assert results[0]["paper_id"] == "p3"

        # Remaining order depends on RRF scores
        paper_ids = [r["paper_id"] for r in results]
        assert set(paper_ids) == {"p1", "p2", "p3", "p4", "p5"}

    def test_search_respects_limit(self) -> None:
        """Should respect limit parameter."""
        fts = FakePapersFTS(results=["p1", "p2", "p3", "p4", "p5"])
        vector_index = FakeVectorIndex(results=[])
        embedder = FakeEmbedder()

        use_case = SearchPapersUseCase(
            papers_fts=fts,
            vector_index=vector_index,
            embedder=embedder,
        )

        results = use_case.search(query="test", limit=3)
        assert len(results) == 3

    def test_search_with_empty_query(self) -> None:
        """Should return empty results for empty query."""
        fts = FakePapersFTS(results=["p1", "p2"])
        vector_index = FakeVectorIndex(results=[])
        embedder = FakeEmbedder()

        use_case = SearchPapersUseCase(
            papers_fts=fts,
            vector_index=vector_index,
            embedder=embedder,
        )

        results = use_case.search(query="", limit=10)
        assert len(results) == 0


class TestFilterByExtractionsUseCase:
    """Test FilterByExtractionsUseCase."""

    def test_filter_by_text_value(self) -> None:
        """Should filter by text extraction value."""
        extraction_store = FakeExtractionStore()
        extraction_store.set_query_result(
            field_path="algorithm_family",
            prompt_version_id="pv1",
            constraints={"value_text": "transformer"},
            paper_ids=["p1", "p2", "p3"],
        )

        use_case = FilterByExtractionsUseCase(extraction_store=extraction_store)

        results = use_case.filter(
            field_path="algorithm_family",
            prompt_version_id="pv1",
            constraints={"value_text": "transformer"},
        )

        assert results == ["p1", "p2", "p3"]

    def test_filter_by_numeric_value(self) -> None:
        """Should filter by numeric extraction value."""
        extraction_store = FakeExtractionStore()
        extraction_store.set_query_result(
            field_path="rigor_rating",
            prompt_version_id="pv1",
            constraints={"value_numeric": 5},
            paper_ids=["p4", "p5"],
        )

        use_case = FilterByExtractionsUseCase(extraction_store=extraction_store)

        results = use_case.filter(
            field_path="rigor_rating",
            prompt_version_id="pv1",
            constraints={"value_numeric": 5},
        )

        assert results == ["p4", "p5"]

    def test_filter_with_no_matches(self) -> None:
        """Should return empty list when no matches."""
        extraction_store = FakeExtractionStore()

        use_case = FilterByExtractionsUseCase(extraction_store=extraction_store)

        results = use_case.filter(
            field_path="nonexistent_field",
            prompt_version_id="pv1",
            constraints={"value_text": "nothing"},
        )

        assert results == []

    def test_filter_with_latest_only_false(self) -> None:
        """Should pass latest_only=False to extraction store."""
        extraction_store = FakeExtractionStore()
        extraction_store.set_query_result(
            field_path="algorithm_family",
            prompt_version_id="pv1",
            constraints={"value_text": "transformer"},
            paper_ids=["p1", "p2"],
        )

        use_case = FilterByExtractionsUseCase(extraction_store=extraction_store)

        results = use_case.filter(
            field_path="algorithm_family",
            prompt_version_id="pv1",
            constraints={"value_text": "transformer"},
            latest_only=False,
        )

        assert results == ["p1", "p2"]


class TestAggregateExtractionsUseCase:
    """Test AggregateExtractionsUseCase."""

    def test_aggregate_count_by_field_value(self) -> None:
        """Should aggregate counts by field value."""
        extraction_store = FakeExtractionStore()
        extraction_store.set_count_result(
            field_path="algorithm_family",
            prompt_version_id="pv1",
            counts={"transformer": 10, "cnn": 5, "rnn": 3},
        )

        use_case = AggregateExtractionsUseCase(extraction_store=extraction_store)

        result = use_case.count_by_value(
            field_path="algorithm_family",
            prompt_version_id="pv1",
        )

        assert result == {"transformer": 10, "cnn": 5, "rnn": 3}

    def test_count_by_value_interface(self) -> None:
        """Should have count_by_value method."""
        extraction_store = FakeExtractionStore()
        use_case = AggregateExtractionsUseCase(extraction_store=extraction_store)

        # Verify method signature
        result = use_case.count_by_value(
            field_path="algorithm_family",
            prompt_version_id="pv1",
        )

        # Should return dict mapping values to counts
        assert isinstance(result, dict)

    def test_average_numeric_interface(self) -> None:
        """Should have average_numeric method."""
        extraction_store = FakeExtractionStore()
        extraction_store.set_average_result(
            field_path="rigor_rating",
            prompt_version_id="pv1",
            average=4.5,
        )

        use_case = AggregateExtractionsUseCase(extraction_store=extraction_store)

        # Verify method signature
        result = use_case.average_numeric(
            field_path="rigor_rating",
            prompt_version_id="pv1",
            group_by=None,
        )

        # Should return average
        assert result == 4.5
