"""Discovery use-cases for finding and importing papers from external sources."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from papers.domain.errors import NotFoundError
from papers.domain.models import PipelineHealth, PipelineStage


class ScholarClient(Protocol):
    """Protocol for scholar search client."""

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
    ) -> list[dict[str, Any]]: ...


class CandidateStore(Protocol):
    """Protocol for candidate storage."""

    def create_candidate(self, fields: dict[str, Any]) -> str: ...
    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None: ...
    def mark_imported(self, candidate_id: str, paper_id: str) -> None: ...
    def mark_rejected(self, candidate_id: str) -> None: ...


class PaperStore(Protocol):
    """Protocol for paper storage."""

    def create_paper(self, fields: dict[str, Any]) -> str: ...
    def get(self, paper_id: str) -> dict[str, Any] | None: ...


class JobQueue(Protocol):
    """Protocol for job queue."""

    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class DiscoverCandidatesUseCase:
    """Discover papers from external sources and store as candidates."""

    scholar_client: ScholarClient
    candidate_store: CandidateStore

    def discover(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
    ) -> list[str]:
        """Search for papers and store as candidates.

        Args:
            query: Search query string
            filters: Optional filters (year_min, year_max, etc.)
            max_results: Maximum number of results to fetch

        Returns:
            List of created candidate IDs
        """
        # Search via scholar client
        results = self.scholar_client.search(
            query=query,
            filters=filters,
            max_results=max_results,
            page_size=100,
        )

        # Store each result as a candidate
        candidate_ids = []
        for result in results:
            candidate_id = str(uuid.uuid4())

            # Prepare candidate fields
            fields = {
                "candidate_id": candidate_id,
                "source": "semantic_scholar",
                "source_paper_id": result["source_paper_id"],
                "title": result["title"],
                "year": result.get("year"),
                "venue": result.get("venue"),
                "authors_json": json.dumps(result.get("authors", [])),
                "abstract": result.get("abstract"),
                "external_ids_json": (
                    json.dumps(result["external_ids"]) if result.get("external_ids") else None
                ),
                "rejected_at": None,
                "imported_paper_id": None,
                "imported_at": None,
            }

            # Store candidate
            self.candidate_store.create_candidate(fields)
            candidate_ids.append(candidate_id)

        return candidate_ids


@dataclass(frozen=True)
class ImportCandidateUseCase:
    """Import a candidate into the corpus as a paper."""

    candidate_store: CandidateStore
    paper_store: PaperStore
    job_queue: JobQueue

    def import_candidate(self, candidate_id: str) -> str:
        """Import candidate as a paper and enqueue download job.

        Args:
            candidate_id: ID of candidate to import

        Returns:
            paper_id of created/existing paper

        Raises:
            NotFoundError: If candidate doesn't exist
            ValueError: If candidate was already rejected
        """
        # Get candidate
        candidate = self.candidate_store.get_candidate(candidate_id)
        if candidate is None:
            raise NotFoundError(f"candidate not found: {candidate_id}")

        # Check if already rejected
        if candidate.get("rejected_at") is not None:
            raise ValueError("cannot import candidate that was already rejected")

        # Check if already imported (idempotency)
        if candidate.get("imported_paper_id"):
            return candidate["imported_paper_id"]

        # Create paper
        paper_id = str(uuid.uuid4())

        # Parse authors JSON if it exists
        authors = []
        if candidate.get("authors_json"):
            try:
                authors = json.loads(candidate["authors_json"])
            except (json.JSONDecodeError, TypeError):
                authors = []

        paper_fields = {
            "paper_id": paper_id,
            "title": candidate["title"],
            "year": candidate.get("year"),
            "venue": candidate.get("venue"),
            "authors": authors,
            "abstract": candidate.get("abstract"),
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }

        self.paper_store.create_paper(paper_fields)

        # Enqueue download job
        self.job_queue.enqueue(
            type="download",
            paper_id=paper_id,
            run_id=None,
            payload={},
        )

        # Mark candidate as imported
        self.candidate_store.mark_imported(candidate_id, paper_id)

        return paper_id


@dataclass(frozen=True)
class RejectCandidateUseCase:
    """Reject a candidate (mark as not interesting)."""

    candidate_store: CandidateStore

    def reject(self, candidate_id: str) -> None:
        """Reject a candidate.

        Args:
            candidate_id: ID of candidate to reject

        Raises:
            NotFoundError: If candidate doesn't exist
            ValueError: If candidate was already imported
        """
        # Get candidate
        candidate = self.candidate_store.get_candidate(candidate_id)
        if candidate is None:
            raise NotFoundError(f"candidate not found: {candidate_id}")

        # Check if already imported
        if candidate.get("imported_paper_id"):
            raise ValueError("cannot reject candidate that was already imported")

        # Mark as rejected (idempotent)
        self.candidate_store.mark_rejected(candidate_id)
