"""Integration test for Phase 4: Discovery → Import → Search flow."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from papers.app.use_cases.discovery import (
    DiscoverCandidatesUseCase,
    ImportCandidateUseCase,
    RejectCandidateUseCase,
)
from papers.app.use_cases.search import SearchPapersUseCase
from papers.domain.models import PipelineStage

# Fake implementations for integration testing


class FakeScholarClient:
    """Fake scholar client with predefined results."""

    def __init__(self) -> None:
        self.search_results = [
            {
                "source_paper_id": "s2_paper1",
                "title": "Attention Is All You Need",
                "year": 2017,
                "venue": "NeurIPS",
                "authors": ["Vaswani et al."],
                "abstract": "The dominant sequence transduction models...",
                "external_ids": {"ArXiv": "1706.03762"},
            },
            {
                "source_paper_id": "s2_paper2",
                "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                "year": 2018,
                "venue": "NAACL",
                "authors": ["Devlin et al."],
                "abstract": "We introduce BERT, a new language representation model...",
                "external_ids": {"ArXiv": "1810.04805"},
            },
            {
                "source_paper_id": "s2_paper3",
                "title": "GPT-3: Language Models are Few-Shot Learners",
                "year": 2020,
                "venue": "NeurIPS",
                "authors": ["Brown et al."],
                "abstract": "Recent work has demonstrated substantial gains...",
                "external_ids": {"ArXiv": "2005.14165"},
            },
        ]

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.search_results[:max_results]


class FakeCandidateStore:
    """Fake candidate store."""

    def __init__(self) -> None:
        self.candidates: dict[str, dict[str, Any]] = {}

    def create_candidate(self, fields: dict[str, Any]) -> str:
        candidate_id = fields["candidate_id"]
        self.candidates[candidate_id] = dict(fields)
        return candidate_id

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def get_candidate_by_source(self, source: str, source_paper_id: str) -> dict[str, Any] | None:
        for candidate in self.candidates.values():
            if (
                candidate.get("source") == source
                and candidate.get("source_paper_id") == source_paper_id
            ):
                return candidate
        return None

    def mark_imported(self, candidate_id: str, paper_id: str) -> None:
        if candidate_id in self.candidates:
            self.candidates[candidate_id]["imported_paper_id"] = paper_id

    def mark_rejected(self, candidate_id: str) -> None:
        if candidate_id in self.candidates:
            from datetime import datetime

            self.candidates[candidate_id]["rejected_at"] = datetime.now()


class FakePaperStore:
    """Fake paper store."""

    def __init__(self) -> None:
        self.papers: dict[str, dict[str, Any]] = {}

    def create_paper(self, fields: dict[str, Any]) -> str:
        paper_id = fields["paper_id"]
        self.papers[paper_id] = dict(fields)
        return paper_id

    def get(self, paper_id: str) -> dict[str, Any] | None:
        return self.papers.get(paper_id)


class FakeJobQueue:
    """Fake job queue."""

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []

    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after=None,
    ) -> str:
        job_id = str(uuid.uuid4())
        self.jobs.append(
            {
                "job_id": job_id,
                "type": type,
                "paper_id": paper_id,
                "run_id": run_id,
                "payload": payload,
            }
        )
        return job_id


class FakePapersFTS:
    """Fake FTS search."""

    def __init__(self) -> None:
        self.indexed_papers: dict[str, dict[str, str]] = {}

    def index_paper(self, paper_id: str, title: str, abstract: str) -> None:
        self.indexed_papers[paper_id] = {"title": title, "abstract": abstract}

    def search(self, query: str, limit: int) -> list[str]:
        # Simple substring matching for testing
        query_lower = query.lower()
        results = []
        for paper_id, data in self.indexed_papers.items():
            if query_lower in data["title"].lower() or (
                data["abstract"] and query_lower in data["abstract"].lower()
            ):
                results.append(paper_id)
        return results[:limit]


class FakeVectorIndex:
    """Fake vector index."""

    def __init__(self) -> None:
        self.embeddings: dict[str, list[float]] = {}

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        self.embeddings[paper_id] = embedding

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        # Return all papers with dummy similarity scores
        results = [(paper_id, 0.9 - i * 0.1) for i, paper_id in enumerate(self.embeddings.keys())]
        return results[:limit]


class FakeEmbedder:
    """Fake embedder."""

    def embed(self, text: str) -> list[float]:
        return [0.1] * 384


@pytest.mark.integration
class TestPhase4DiscoveryFlow:
    """Integration test for discovery → import → search flow."""

    def test_end_to_end_discovery_import_search(self) -> None:
        """Test complete flow from discovery to search."""
        # Setup fake dependencies
        scholar_client = FakeScholarClient()
        candidate_store = FakeCandidateStore()
        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()
        papers_fts = FakePapersFTS()
        vector_index = FakeVectorIndex()
        embedder = FakeEmbedder()

        # Step 1: Discover candidates
        discover_uc = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )

        candidate_ids = discover_uc.discover(
            query="transformer neural networks",
            filters={"year_min": 2017},
            max_results=3,
        )

        assert len(candidate_ids) == 3

        # Verify candidates were stored
        for candidate_id in candidate_ids:
            candidate = candidate_store.get_candidate(candidate_id)
            assert candidate is not None
            assert candidate["source"] == "semantic_scholar"
            assert candidate["imported_paper_id"] is None

        # Step 2: Import first two candidates
        import_uc = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )

        paper_id1 = import_uc.import_candidate(candidate_ids[0])
        paper_id2 = import_uc.import_candidate(candidate_ids[1])

        # Verify papers were created
        paper1 = paper_store.get(paper_id1)
        assert paper1 is not None
        assert paper1["title"] == "Attention Is All You Need"
        assert paper1["pipeline_stage"] == str(PipelineStage.imported)

        paper2 = paper_store.get(paper_id2)
        assert paper2 is not None
        assert paper2["title"] == "BERT: Pre-training of Deep Bidirectional Transformers"

        # Verify download jobs were enqueued
        assert len(job_queue.jobs) == 2
        assert job_queue.jobs[0]["type"] == "download"
        assert job_queue.jobs[0]["paper_id"] == paper_id1
        assert job_queue.jobs[1]["paper_id"] == paper_id2

        # Verify candidates were marked imported
        cand1 = candidate_store.get_candidate(candidate_ids[0])
        assert cand1 is not None
        assert cand1["imported_paper_id"] == paper_id1

        # Step 3: Reject third candidate
        reject_uc = RejectCandidateUseCase(candidate_store=candidate_store)
        reject_uc.reject(candidate_ids[2])

        cand3 = candidate_store.get_candidate(candidate_ids[2])
        assert cand3 is not None
        assert cand3["rejected_at"] is not None

        # Step 4: Index papers for search (simulating pipeline completion)
        papers_fts.index_paper(paper_id1, paper1["title"], paper1.get("abstract", ""))
        papers_fts.index_paper(paper_id2, paper2["title"], paper2.get("abstract", ""))

        # Add embeddings
        vector_index.upsert(paper_id1, embedder.embed(paper1["title"]))
        vector_index.upsert(paper_id2, embedder.embed(paper2["title"]))

        # Step 5: Search for papers
        search_uc = SearchPapersUseCase(
            papers_fts=papers_fts,
            vector_index=vector_index,
            embedder=embedder,
        )

        # Search for "BERT"
        results = search_uc.search(query="BERT", limit=10)

        assert len(results) > 0
        # BERT paper should be in results
        paper_ids_in_results = [r["paper_id"] for r in results]
        assert paper_id2 in paper_ids_in_results

        # Search for "attention"
        results = search_uc.search(query="attention", limit=10)
        assert len(results) > 0
        paper_ids_in_results = [r["paper_id"] for r in results]
        assert paper_id1 in paper_ids_in_results

    def test_import_is_idempotent(self) -> None:
        """Verify import can be called multiple times safely."""
        scholar_client = FakeScholarClient()
        candidate_store = FakeCandidateStore()
        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        # Discover
        discover_uc = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )
        candidate_ids = discover_uc.discover(query="test", filters={}, max_results=1)

        # Import same candidate twice
        import_uc = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )
        paper_id1 = import_uc.import_candidate(candidate_ids[0])
        paper_id2 = import_uc.import_candidate(candidate_ids[0])

        # Should return same paper_id
        assert paper_id1 == paper_id2
        # Only one paper should exist
        assert len(paper_store.papers) == 1
        # Only one job should be enqueued
        assert len(job_queue.jobs) == 1

    def test_cannot_import_rejected_candidate(self) -> None:
        """Verify rejected candidates cannot be imported."""
        scholar_client = FakeScholarClient()
        candidate_store = FakeCandidateStore()
        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        # Discover
        discover_uc = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )
        candidate_ids = discover_uc.discover(query="test", filters={}, max_results=1)

        # Reject first
        reject_uc = RejectCandidateUseCase(candidate_store=candidate_store)
        reject_uc.reject(candidate_ids[0])

        # Try to import
        import_uc = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )

        with pytest.raises(ValueError, match="already rejected"):
            import_uc.import_candidate(candidate_ids[0])

    def test_cannot_reject_imported_candidate(self) -> None:
        """Verify imported candidates cannot be rejected."""
        scholar_client = FakeScholarClient()
        candidate_store = FakeCandidateStore()
        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        # Discover
        discover_uc = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )
        candidate_ids = discover_uc.discover(query="test", filters={}, max_results=1)

        # Import first
        import_uc = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )
        import_uc.import_candidate(candidate_ids[0])

        # Try to reject
        reject_uc = RejectCandidateUseCase(candidate_store=candidate_store)

        with pytest.raises(ValueError, match="already imported"):
            reject_uc.reject(candidate_ids[0])
