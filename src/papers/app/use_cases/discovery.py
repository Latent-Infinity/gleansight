"""Discovery use-cases for finding and importing papers from external sources."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from papers.app import ports
from papers.domain.errors import ConfigurationError, NotFoundError, ValidationError
from papers.domain.models import PipelineHealth, PipelineStage


class ScholarClient(Protocol):
    """Protocol for scholar search client."""

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...


class CandidateStore(Protocol):
    """Protocol for candidate storage."""

    def create_candidate(self, fields: dict[str, Any]) -> str: ...
    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None: ...
    def get_candidate_by_source(
        self, source: str, source_paper_id: str
    ) -> dict[str, Any] | None: ...
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


class PaperExternalIdStore(Protocol):
    """Protocol for storing paper external identifiers."""

    def create_external_ids(self, paper_id: str, external_ids: dict[str, str]) -> None: ...

    def get_external_ids(self, paper_id: str) -> dict[str, str]: ...


class CandidateImporter(Protocol):
    """Atomic boundary for importing a candidate into the paper corpus."""

    def import_candidate(self, candidate_id: str) -> str: ...


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
        page_size: int | None = None,
        offset: int = 0,
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
        effective_page_size = (
            min(100, max_results) if page_size is None else max(1, min(100, page_size))
        )
        results = self.scholar_client.search(
            query=query,
            filters=filters,
            max_results=max_results,
            page_size=effective_page_size,
            offset=max(0, offset),
        )

        # Store each result as a candidate
        candidate_ids = []
        for result in results:
            source_paper_id = result.get("source_paper_id") or ""
            if not source_paper_id.strip():
                continue
            existing = self.candidate_store.get_candidate_by_source(
                "semantic_scholar",
                source_paper_id,
            )
            if existing is not None:
                candidate_ids.append(existing["candidate_id"])
                continue

            candidate_id = str(uuid.uuid4())

            # Prepare candidate fields
            fields = {
                "candidate_id": candidate_id,
                "source": "semantic_scholar",
                "source_paper_id": source_paper_id,
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
            created_candidate_id = self.candidate_store.create_candidate(fields)
            candidate_ids.append(created_candidate_id)

        return candidate_ids


@dataclass(frozen=True)
class ImportCandidateUseCase:
    """Import a candidate into the corpus as a paper."""

    candidate_store: CandidateStore
    paper_store: PaperStore
    job_queue: JobQueue
    external_id_store: PaperExternalIdStore | None = None
    atomic_importer: CandidateImporter | None = None
    project_store: ports.ProjectStore | None = None
    tag_store: ports.TagStore | None = None
    atomic_candidate_import: ports.AtomicCandidateImport | None = None

    def import_candidate(
        self,
        candidate_id: str,
        *,
        project_ids: list[str] | None = None,
        tag_ids: list[str] | None = None,
    ) -> str:
        candidate = self.candidate_store.get_candidate(candidate_id)
        if candidate is None:
            raise NotFoundError(f"candidate not found: {candidate_id}")
        if candidate.get("rejected_at") is not None:
            raise ValueError("cannot import candidate that was already rejected")

        resolved_projects = _deduplicate_membership_ids(project_ids, "project")
        resolved_tags = _deduplicate_membership_ids(tag_ids, "tag")
        self._require_membership_ids(resolved_projects, resolved_tags)
        if (resolved_projects or resolved_tags) and self.atomic_candidate_import is None:
            raise ConfigurationError("taxonomy attachments require AtomicCandidateImport")

        if candidate.get("imported_paper_id"):
            paper_id = str(candidate["imported_paper_id"])
            if self.atomic_candidate_import is not None:
                self.atomic_candidate_import.attach_to_imported(
                    paper_id=paper_id,
                    project_ids=resolved_projects,
                    tag_ids=resolved_tags,
                )
            return paper_id

        authors: list[Any] = []
        if candidate.get("authors_json"):
            try:
                authors = json.loads(candidate["authors_json"])
            except (json.JSONDecodeError, TypeError):
                authors = []
        external_ids: dict[str, str] = {}
        if candidate.get("external_ids_json"):
            try:
                parsed = json.loads(candidate["external_ids_json"])
            except (json.JSONDecodeError, TypeError):
                parsed = {}
            if isinstance(parsed, dict):
                external_ids = {
                    str(kind): str(value) for kind, value in parsed.items() if value is not None
                }

        paper_fields = {
            "title": candidate["title"],
            "year": candidate.get("year"),
            "venue": candidate.get("venue"),
            "authors": authors,
            "abstract": candidate.get("abstract"),
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
        }

        if self.atomic_candidate_import is not None:
            return self.atomic_candidate_import.import_new(
                candidate_id=candidate_id,
                paper_fields=paper_fields,
                external_ids=external_ids,
                project_ids=resolved_projects,
                tag_ids=resolved_tags,
            )

        if self.atomic_importer is not None:
            return self.atomic_importer.import_candidate(candidate_id)

        paper_id = str(uuid.uuid4())
        self.paper_store.create_paper(
            {
                "paper_id": paper_id,
                **paper_fields,
            }
        )
        if self.external_id_store and external_ids:
            self.external_id_store.create_external_ids(paper_id, external_ids)
        self.job_queue.enqueue(
            type="download",
            paper_id=paper_id,
            run_id=None,
            payload={"external_ids": external_ids} if external_ids else {},
        )
        self.candidate_store.mark_imported(candidate_id, paper_id)
        return paper_id

    def _require_membership_ids(self, project_ids: list[str], tag_ids: list[str]) -> None:
        for project_id in project_ids:
            if self.project_store is None or self.project_store.get(project_id) is None:
                raise NotFoundError(f"project not found: {project_id}")
        for tag_id in tag_ids:
            if self.tag_store is None or self.tag_store.get(tag_id) is None:
                raise NotFoundError(f"tag not found: {tag_id}")


def _deduplicate_membership_ids(values: list[str] | None, kind: str) -> list[str]:
    resolved = list(dict.fromkeys(values or []))
    if len(resolved) > 100:
        raise ValidationError(f"too many {kind} IDs: maximum is 100")
    return resolved


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
