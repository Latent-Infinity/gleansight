from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from nsqd.domain.acquisition import CANDIDATES_PER_BATCH


class _DiscoverCandidates(Protocol):
    def discover(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int | None = None,
        offset: int = 0,
    ) -> list[str]: ...


class _ImportCandidate(Protocol):
    def import_candidate(self, candidate_id: str) -> str: ...


class _RunAnalysis(Protocol):
    def __call__(
        self,
        *,
        paper_id: str,
        prompt_id: str,
        prompt_version_id: str | None,
        profile_id: str,
        model_name: str,
        force: bool = False,
    ) -> str: ...


class _PaperStore(Protocol):
    def get(self, paper_id: str) -> dict[str, Any] | None: ...


class _CandidateLookup(Protocol):
    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class AnalysisDefaults:
    prompt_id: str
    profile_id: str
    model_name: str
    prompt_version_id: str | None = None


@dataclass(frozen=True)
class PapersAcquisitionBridge:
    discover_candidates: _DiscoverCandidates
    import_candidate: _ImportCandidate
    run_analysis: _RunAnalysis
    paper_store: _PaperStore
    analysis_defaults: AnalysisDefaults | None = None
    get_markdown: Callable[[str], str | None] | None = None
    candidate_lookup: _CandidateLookup | None = None

    def discover(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        candidate_ids = self.discover_candidates.discover(
            query,
            filters,
            max_results=CANDIDATES_PER_BATCH,
        )
        lookup = self.candidate_lookup
        if lookup is None:
            store = getattr(self.discover_candidates, "candidate_store", None)
            lookup = store if hasattr(store, "get_candidate") else None
        if lookup is None:
            raise ValueError("candidate lookup is required for acquisition discovery")
        discovered: list[dict[str, Any]] = []
        for candidate_id in candidate_ids:
            row = lookup.get_candidate(candidate_id)
            if row is None:
                raise ValueError(f"candidate metadata is unavailable: {candidate_id}")
            source_paper_id = row.get("source_paper_id")
            if not isinstance(source_paper_id, str) or not source_paper_id.strip():
                raise ValueError(f"candidate source_paper_id is required: {candidate_id}")
            item = {
                "candidate_id": candidate_id,
                "source_paper_id": source_paper_id.strip(),
                "title": None if row is None else row.get("title"),
                "abstract": None if row is None else row.get("abstract"),
            }
            discovered.append({k: v for k, v in item.items() if v is not None})
        return discovered

    def shortlist(self, candidates: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates[:limit]):
            selected.append(
                {
                    **candidate,
                    "review_status": "pending",
                    "llm_rank": index + 1,
                }
            )
        return selected

    def stage_import(self, candidate: dict[str, Any]) -> str:
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError("candidate_id is required")
        return self.import_candidate.import_candidate(candidate_id.strip())

    def enqueue_analyze(self, paper_id: str) -> None:
        defaults = self.analysis_defaults
        if defaults is None:
            raise ValueError("analysis defaults are required")
        self.run_analysis(
            paper_id=paper_id,
            prompt_id=defaults.prompt_id,
            prompt_version_id=defaults.prompt_version_id,
            profile_id=defaults.profile_id,
            model_name=defaults.model_name,
        )

    def draft_projection(self, paper_id: str) -> dict[str, Any]:
        paper = self.paper_store.get(paper_id) or {}
        markdown = self.get_markdown(paper_id) if self.get_markdown is not None else None
        paraphrase = str(markdown or paper.get("abstract") or paper.get("title") or "").strip()
        return {
            "paper_id": paper_id,
            "review_status": "pending",
            "paraphrase": paraphrase,
            "paraphrase_source": "model",
        }
