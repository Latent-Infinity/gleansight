from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pytest

from papers.app.use_cases.discovery import (
    DiscoverCandidatesUseCase,
    ImportCandidateUseCase,
    RejectCandidateUseCase,
)
from papers.domain.errors import NotFoundError
from papers.domain.models import PipelineStage


class FakeCandidateStore:
    """Fake candidate store for testing."""

    def __init__(self) -> None:
        self.candidates: dict[str, dict[str, Any]] = {}

    def create_candidate(self, fields: dict[str, Any]) -> str:
        candidate_id = fields["candidate_id"]
        self.candidates[candidate_id] = dict(fields)
        return candidate_id

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def get_candidate_by_source(
        self, source: str, source_paper_id: str
    ) -> dict[str, Any] | None:
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
            self.candidates[candidate_id]["imported_at"] = datetime.now()

    def mark_rejected(self, candidate_id: str) -> None:
        if candidate_id in self.candidates:
            self.candidates[candidate_id]["rejected_at"] = datetime.now()


class FakePaperStore:
    """Fake paper store for testing."""

    def __init__(self) -> None:
        self.papers: dict[str, dict[str, Any]] = {}

    def create_paper(self, fields: dict[str, Any]) -> str:
        paper_id = fields["paper_id"]
        self.papers[paper_id] = dict(fields)
        return paper_id

    def get(self, paper_id: str) -> dict[str, Any] | None:
        return self.papers.get(paper_id)


class FakeJobQueue:
    """Fake job queue for testing."""

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []

    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        self.jobs.append(
            {
                "job_id": job_id,
                "type": type,
                "paper_id": paper_id,
                "run_id": run_id,
                "payload": payload,
                "run_after": run_after,
            }
        )
        return job_id


class FakeScholarClient:
    """Fake scholar client for testing."""

    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results or []
        self.call_count = 0

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        self.call_count += 1
        return self.results[:max_results]


class TestDiscoverCandidatesUseCase:
    """Test DiscoverCandidatesUseCase."""

    def test_discover_creates_candidate_records(self) -> None:
        """Should call ScholarClient and store candidates."""
        scholar_results = [
            {
                "source_paper_id": "s2_abc123",
                "title": "Deep Learning Paper",
                "year": 2020,
                "venue": "NeurIPS",
                "authors": ["Alice Smith", "Bob Jones"],
                "abstract": "This paper presents...",
                "external_ids": {"ArXiv": "2001.12345"},
            },
            {
                "source_paper_id": "s2_def456",
                "title": "Attention Mechanisms",
                "year": 2019,
                "venue": None,
                "authors": ["Charlie Brown"],
                "abstract": None,
                "external_ids": None,
            },
        ]

        scholar_client = FakeScholarClient(results=scholar_results)
        candidate_store = FakeCandidateStore()

        use_case = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )

        candidate_ids = use_case.discover(
            query="deep learning",
            filters={"year_min": 2018},
            max_results=10,
        )

        assert len(candidate_ids) == 2
        assert scholar_client.call_count == 1

        # Verify candidates were stored
        cand1 = candidate_store.get_candidate(candidate_ids[0])
        assert cand1 is not None
        assert cand1["source"] == "semantic_scholar"
        assert cand1["source_paper_id"] == "s2_abc123"
        assert cand1["title"] == "Deep Learning Paper"
        assert cand1["year"] == 2020
        assert cand1["venue"] == "NeurIPS"
        assert cand1["imported_paper_id"] is None
        assert cand1["rejected_at"] is None

        cand2 = candidate_store.get_candidate(candidate_ids[1])
        assert cand2 is not None
        assert cand2["source_paper_id"] == "s2_def456"

    def test_discover_with_no_results(self) -> None:
        """Should handle no results from scholar client."""
        scholar_client = FakeScholarClient(results=[])
        candidate_store = FakeCandidateStore()

        use_case = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )

        candidate_ids = use_case.discover(
            query="nonexistent topic",
            filters={},
            max_results=10,
        )

        assert len(candidate_ids) == 0

    def test_discover_skips_missing_source_paper_id(self) -> None:
        """Should skip results missing source_paper_id to avoid collisions."""
        scholar_results = [
            {
                "source_paper_id": "",
                "title": "Missing ID",
                "year": 2020,
                "venue": "NeurIPS",
                "authors": ["Alice Smith"],
                "abstract": "This paper presents...",
                "external_ids": {"ArXiv": "2001.12345"},
            }
        ]

        scholar_client = FakeScholarClient(results=scholar_results)
        candidate_store = FakeCandidateStore()

        use_case = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )

        candidate_ids = use_case.discover(
            query="deep learning",
            filters={},
            max_results=10,
        )

        assert candidate_ids == []

    def test_discover_reuses_existing_candidate(self) -> None:
        """Should reuse existing candidate when source_paper_id already stored."""
        scholar_results = [
            {
                "source_paper_id": "s2_abc123",
                "title": "Deep Learning Paper",
                "year": 2020,
                "venue": "NeurIPS",
                "authors": ["Alice Smith", "Bob Jones"],
                "abstract": "This paper presents...",
                "external_ids": {"ArXiv": "2001.12345"},
            }
        ]

        scholar_client = FakeScholarClient(results=scholar_results)
        candidate_store = FakeCandidateStore()
        existing_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Old Title",
                "year": 2019,
                "venue": "OldConf",
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        use_case = DiscoverCandidatesUseCase(
            scholar_client=scholar_client,
            candidate_store=candidate_store,
        )

        candidate_ids = use_case.discover(
            query="deep learning",
            filters={},
            max_results=10,
        )

        assert candidate_ids == [existing_id]


class TestImportCandidateUseCase:
    """Test ImportCandidateUseCase."""

    def test_import_creates_paper_and_enqueues_job(self) -> None:
        """Should create paper and enqueue download job."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": "ACL",
                "authors_json": '["Alice"]',
                "abstract": "Abstract text",
                "external_ids_json": '{"ArXiv": "2001.12345"}',
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        use_case = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )

        paper_id = use_case.import_candidate(candidate_id)

        # Verify paper was created
        paper = paper_store.get(paper_id)
        assert paper is not None
        assert paper["title"] == "Test Paper"
        assert paper["year"] == 2020
        assert paper["venue"] == "ACL"
        assert paper["pipeline_stage"] == str(PipelineStage.imported)

        # Verify download job was enqueued
        assert len(job_queue.jobs) == 1
        job = job_queue.jobs[0]
        assert job["type"] == "download"
        assert job["paper_id"] == paper_id

        # Verify candidate was marked imported
        candidate = candidate_store.get_candidate(candidate_id)
        assert candidate is not None
        assert candidate["imported_paper_id"] == paper_id
        assert candidate["imported_at"] is not None

    def test_import_is_idempotent(self) -> None:
        """Should be idempotent - second import returns same paper_id."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": None,
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        use_case = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )

        paper_id1 = use_case.import_candidate(candidate_id)
        paper_id2 = use_case.import_candidate(candidate_id)

        assert paper_id1 == paper_id2
        assert len(paper_store.papers) == 1
        assert len(job_queue.jobs) == 1  # Job should only be enqueued once

    def test_import_raises_if_candidate_not_found(self) -> None:
        """Should raise NotFoundError if candidate doesn't exist."""
        use_case = ImportCandidateUseCase(
            candidate_store=FakeCandidateStore(),
            paper_store=FakePaperStore(),
            job_queue=FakeJobQueue(),
        )

        with pytest.raises(NotFoundError):
            use_case.import_candidate("nonexistent_id")

    def test_import_raises_if_candidate_already_rejected(self) -> None:
        """Should raise error if candidate was rejected."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": None,
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": datetime.now(),  # Already rejected
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        use_case = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=FakePaperStore(),
            job_queue=FakeJobQueue(),
        )

        with pytest.raises(ValueError) as exc_info:
            use_case.import_candidate(candidate_id)

        assert "already rejected" in str(exc_info.value).lower()

    def test_import_preserves_external_ids_in_job_payload(self) -> None:
        """Should include external IDs in download job payload."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": "ACL",
                "authors_json": '["Alice"]',
                "abstract": "Abstract text",
                "external_ids_json": '{"ArXiv": "2001.12345", "DOI": "10.1234/abc"}',
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        use_case = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )

        use_case.import_candidate(candidate_id)

        # Verify external IDs are in job payload
        assert len(job_queue.jobs) == 1
        job = job_queue.jobs[0]
        assert job["payload"]["external_ids"] == {"ArXiv": "2001.12345", "DOI": "10.1234/abc"}

    def test_import_stores_external_ids_when_store_provided(self) -> None:
        """Should store external IDs when external_id_store is provided."""

        class FakeExternalIdStore:
            def __init__(self) -> None:
                self.external_ids: dict[str, dict[str, str]] = {}

            def create_external_ids(
                self, paper_id: str, external_ids: dict[str, str]
            ) -> None:
                self.external_ids[paper_id] = external_ids

            def get_external_ids(self, paper_id: str) -> dict[str, str]:
                return self.external_ids.get(paper_id, {})

        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": "ACL",
                "authors_json": '["Alice"]',
                "abstract": "Abstract text",
                "external_ids_json": '{"ArXiv": "2001.12345"}',
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()
        external_id_store = FakeExternalIdStore()

        use_case = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
            external_id_store=external_id_store,
        )

        paper_id = use_case.import_candidate(candidate_id)

        # Verify external IDs were stored
        assert external_id_store.get_external_ids(paper_id) == {"ArXiv": "2001.12345"}

    def test_import_handles_empty_external_ids(self) -> None:
        """Should handle candidate with no external IDs."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": None,
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        paper_store = FakePaperStore()
        job_queue = FakeJobQueue()

        use_case = ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=paper_store,
            job_queue=job_queue,
        )

        paper_id = use_case.import_candidate(candidate_id)

        # Should succeed and have empty payload
        assert paper_id is not None
        assert len(job_queue.jobs) == 1
        assert job_queue.jobs[0]["payload"] == {}


class TestRejectCandidateUseCase:
    """Test RejectCandidateUseCase."""

    def test_reject_marks_candidate_rejected(self) -> None:
        """Should mark candidate as rejected."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": None,
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        use_case = RejectCandidateUseCase(candidate_store=candidate_store)
        use_case.reject(candidate_id)

        candidate = candidate_store.get_candidate(candidate_id)
        assert candidate is not None
        assert candidate["rejected_at"] is not None

    def test_reject_is_idempotent(self) -> None:
        """Should be idempotent - can reject multiple times."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": None,
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }
        )

        use_case = RejectCandidateUseCase(candidate_store=candidate_store)
        use_case.reject(candidate_id)
        first_rejected_at = candidate_store.get_candidate(candidate_id)["rejected_at"]

        use_case.reject(candidate_id)
        second_rejected_at = candidate_store.get_candidate(candidate_id)["rejected_at"]

        assert first_rejected_at is not None
        assert second_rejected_at is not None

    def test_reject_raises_if_candidate_not_found(self) -> None:
        """Should raise NotFoundError if candidate doesn't exist."""
        use_case = RejectCandidateUseCase(candidate_store=FakeCandidateStore())

        with pytest.raises(NotFoundError):
            use_case.reject("nonexistent_id")

    def test_reject_raises_if_already_imported(self) -> None:
        """Should raise error if candidate was already imported."""
        candidate_store = FakeCandidateStore()
        candidate_id = candidate_store.create_candidate(
            {
                "candidate_id": str(uuid.uuid4()),
                "source": "semantic_scholar",
                "source_paper_id": "s2_abc123",
                "title": "Test Paper",
                "year": 2020,
                "venue": None,
                "authors_json": "[]",
                "abstract": None,
                "external_ids_json": None,
                "rejected_at": None,
                "imported_paper_id": "paper_123",  # Already imported
                "imported_at": datetime.now(),
            }
        )

        use_case = RejectCandidateUseCase(candidate_store=candidate_store)

        with pytest.raises(ValueError) as exc_info:
            use_case.reject(candidate_id)

        assert "already imported" in str(exc_info.value).lower()
