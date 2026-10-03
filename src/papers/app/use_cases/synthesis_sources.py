from __future__ import annotations

import hashlib
from dataclasses import dataclass

from papers.app.ports import BlobStore, Embedder, PaperProjectStore, PaperStore, VectorIndex
from papers.domain.ideation_evidence import _section_excerpts
from papers.domain.investigation_evidence import ContractValueError
from papers.domain.synthesis_grounding import GroundedSource


@dataclass(frozen=True, slots=True)
class RetrievedPaper:
    paper_id: str
    title: str
    markdown: bytes

    def excerpts(self) -> tuple[GroundedSource, ...]:
        digest = hashlib.sha256(self.markdown).hexdigest()
        return tuple(
            GroundedSource(
                excerpt_id=f"{self.paper_id}:{digest[:12]}:e{index:03d}",
                paper_id=self.paper_id,
                title=self.title,
                section=section,
                byte_start=start,
                byte_end=end,
                sha256=hashlib.sha256(quote.encode()).hexdigest(),
                quote=quote,
                markdown_sha256=digest,
                page=None,
            )
            for index, (section, start, end, quote) in enumerate(
                _section_excerpts(self.markdown.decode("utf-8"), 2400, 8), start=1
            )
        )


@dataclass(frozen=True, slots=True)
class SynthesisRetrieval:
    embedder: Embedder
    vector_index: VectorIndex
    paper_store: PaperStore
    blob_store: BlobStore
    paper_project_store: PaperProjectStore | None

    def retrieve(
        self, question: str, project_id: str | None, limit: int
    ) -> tuple[GroundedSource, ...]:
        return tuple(
            source
            for paper in self.retrieve_papers(question, project_id, limit)
            for source in paper.excerpts()
        )

    def retrieve_papers(
        self, question: str, project_id: str | None, limit: int
    ) -> tuple[RetrievedPaper, ...]:
        allowed: set[str] | None = None
        if project_id is not None:
            if self.paper_project_store is None:
                raise ContractValueError("project scoping is not configured")
            allowed = set(self.paper_project_store.list_paper_ids(project_id))
        if limit < 1 or allowed == set():
            return ()
        embedding = self.embedder.embed(question)
        seen: set[str] = set()
        found: list[RetrievedPaper] = []
        query_limit = limit
        while len(found) < limit:
            if allowed is not None:
                query_limit = min(query_limit, len(allowed))
            retrieved = self.vector_index.query(embedding, query_limit, allowed_ids=allowed)
            previous = len(seen)
            for paper_id, _score in retrieved:
                if paper_id in seen:
                    continue
                seen.add(paper_id)
                if allowed is not None and paper_id not in allowed:
                    continue
                paper = self.paper_store.get(paper_id)
                path = self.blob_store.get_markdown_path(paper_id)
                if paper is None or path is None:
                    continue
                try:
                    raw = path.read_bytes()
                    markdown = raw.decode("utf-8")
                except (OSError, UnicodeError):
                    continue
                if not _section_excerpts(markdown, 2400, 8):
                    continue
                found.append(RetrievedPaper(paper_id, str(paper.get("title") or "Untitled"), raw))
                if len(found) == limit:
                    break
            if len(retrieved) < query_limit or len(seen) == previous:
                break
            next_limit = query_limit * 2
            if allowed is not None:
                next_limit = min(next_limit, len(allowed))
            if next_limit == query_limit:
                break
            query_limit = next_limit
        return tuple(found)
