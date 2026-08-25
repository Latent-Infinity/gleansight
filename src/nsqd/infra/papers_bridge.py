from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from nsqd.domain.acquisition import CANDIDATES_PER_BATCH

DRAFT_PARAPHRASE_PROMPT = (
    "Draft a one-paragraph mechanism paraphrase for the paper. Do not mark the draft as approved."
)
SHORTLIST_PROMPT = (
    "Rank these discovery candidates for the insufficiency query. "
    "Return a JSON array of candidate_id strings, best first. "
    "Do not mark any candidate approved. Use only the given ids."
)
MAX_DRAFT_SOURCE_CHARS = 12_000
MAX_DRAFT_PARAPHRASE_CHARS = 2_000


def _parse_ranked_ids(text: str) -> list[str]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        fence = stripped.rfind("```")
        if fence >= 0:
            stripped = stripped[:fence]
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("shortlist ranking is not a JSON array")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, list) or any(
        not isinstance(item, str) or not item.strip() for item in data
    ):
        raise ValueError("shortlist ranking must be a JSON array of ids")
    return [item.strip() for item in data]


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


class _LLMClient(Protocol):
    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> Any: ...


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
    llm_client: _LLMClient | None = None
    llm_profile: dict[str, Any] | None = None
    draft_prompt: str = DRAFT_PARAPHRASE_PROMPT
    draft_timeout_s: int = 120
    shortlist_prompt: str = SHORTLIST_PROMPT

    @staticmethod
    def _bounded_draft_source(source_text: str) -> str:
        return source_text[:MAX_DRAFT_SOURCE_CHARS]

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

    def shortlist(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
        insufficiency_query: str,
        filters: dict[str, Any],
        failure_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        if self.llm_client is None:
            raise ValueError("llm client is required to shortlist candidates")
        defaults = self.analysis_defaults
        if defaults is None:
            raise ValueError("analysis defaults are required")
        known = {
            str(candidate["candidate_id"]): candidate
            for candidate in candidates
            if isinstance(candidate.get("candidate_id"), str) and candidate["candidate_id"].strip()
        }
        payload = [
            {
                "candidate_id": candidate_id,
                "title": known[candidate_id].get("title"),
                "abstract": known[candidate_id].get("abstract"),
            }
            for candidate_id in known
        ]
        context_payload = {
            "insufficiency_query": insufficiency_query,
            "filters": filters,
            "failure_context": failure_context,
            "candidates": payload,
        }
        response = self.llm_client.complete(
            prompt=(
                f"{self.shortlist_prompt}\n\n{json.dumps(context_payload, ensure_ascii=False)}"
            ),
            profile=dict(self.llm_profile or {}),
            model=defaults.model_name,
            timeout_s=self.draft_timeout_s,
        )
        ranked_ids = _parse_ranked_ids(str(getattr(response, "text", "") or ""))
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate_id in ranked_ids:
            if candidate_id in seen or candidate_id not in known:
                continue
            seen.add(candidate_id)
            selected.append(
                {
                    **known[candidate_id],
                    "review_status": "pending",
                    "llm_rank": len(selected) + 1,
                }
            )
            if len(selected) >= limit:
                break
        if not selected:
            raise ValueError("shortlist ranking produced no known candidate ids")
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
        if self.llm_client is None:
            raise ValueError("llm client is required to draft a paraphrase")
        defaults = self.analysis_defaults
        if defaults is None:
            raise ValueError("analysis defaults are required")
        paper = self.paper_store.get(paper_id) or {}
        markdown = self.get_markdown(paper_id) if self.get_markdown is not None else None
        source_text = str(markdown or paper.get("abstract") or paper.get("title") or "").strip()
        if not source_text:
            raise ValueError("paper text is required to draft a paraphrase")
        bounded_source = self._bounded_draft_source(source_text)
        response = self.llm_client.complete(
            prompt=f"{self.draft_prompt}\n\n{bounded_source}",
            profile=dict(self.llm_profile or {}),
            model=defaults.model_name,
            timeout_s=self.draft_timeout_s,
        )
        paraphrase = str(getattr(response, "text", "") or "").strip()
        if not paraphrase:
            raise ValueError("draft paraphrase is empty")
        if len(paraphrase) > MAX_DRAFT_PARAPHRASE_CHARS:
            raise ValueError("draft paraphrase is too long")
        return {
            "paper_id": paper_id,
            "review_status": "pending",
            "paraphrase": paraphrase,
            "paraphrase_source": "model",
        }
