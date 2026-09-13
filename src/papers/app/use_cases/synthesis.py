from __future__ import annotations

from typing import Any

from papers.app.ports import (
    BlobStore,
    Embedder,
    LLMClient,
    PaperProjectStore,
    PaperStore,
    VectorIndex,
)
from papers.domain.investigation_plan import SourceReference
from papers.domain.investigation_prompt import (
    build_investigation_plan_prompt,
    investigation_plan_schema,
)
from papers.domain.investigation_renderer import render_investigation_plan_markdown
from papers.domain.investigation_validation import (
    InvestigationPlanValidationContext,
    normalize_investigation_question,
    parse_investigation_plan_json,
)


class SynthesizeFromCorpusUseCase:
    def __init__(
        self,
        embedder: Embedder,
        vector_index: VectorIndex,
        paper_store: PaperStore,
        blob_store: BlobStore,
        llm_client: LLMClient,
        paper_project_store: PaperProjectStore | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_index = vector_index
        self.paper_store = paper_store
        self.blob_store = blob_store
        self.llm_client = llm_client
        self.paper_project_store = paper_project_store

    def synthesize(
        self,
        question: str,
        project_id: str | None = None,
        tags: list[str] | None = None,
        num_retrieved_docs: int = 5,
        llm_profile: dict[str, Any] | None = None,
        llm_model: str = "gpt-4o-mini",
        investigation_plan: bool = False,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Synthesize an answer from the most relevant readable corpus documents."""
        if num_retrieved_docs < 1:
            return "No relevant documents found.", []

        query_embedding = self.embedder.embed(question)
        allowed_ids: set[str] | None = None
        if project_id is not None:
            if self.paper_project_store is None:
                raise ValueError("project scoping is not configured")
            allowed_ids = set(self.paper_project_store.list_paper_ids(project_id))

        sources: list[dict[str, Any]] = []
        context_parts: list[str] = []
        seen_paper_ids: set[str] = set()
        query_limit = num_retrieved_docs
        maximum_candidates = len(allowed_ids) if allowed_ids is not None else None

        while len(sources) < num_retrieved_docs:
            if maximum_candidates is not None:
                if maximum_candidates == 0:
                    break
                query_limit = min(query_limit, maximum_candidates)

            retrieved = self.vector_index.query(
                query_embedding,
                query_limit,
                allowed_ids=allowed_ids,
            )
            new_candidate_found = False
            for paper_id, _score in retrieved:
                if paper_id in seen_paper_ids:
                    continue
                seen_paper_ids.add(paper_id)
                new_candidate_found = True
                if allowed_ids is not None and paper_id not in allowed_ids:
                    continue
                paper = self.paper_store.get(paper_id)
                if paper is None:
                    continue
                markdown_path = self.blob_store.get_markdown_path(paper_id)
                if markdown_path is None or not markdown_path.exists():
                    continue
                try:
                    markdown_content = markdown_path.read_text()
                except OSError:
                    continue
                title = str(paper.get("title") or "Untitled")
                context_parts.append(f"Paper: {title}\nContent: {markdown_content}\n---")
                sources.append({"paper_id": paper_id, "title": title})
                if len(sources) == num_retrieved_docs:
                    break

            if len(sources) == num_retrieved_docs:
                break
            if len(retrieved) < query_limit or not new_candidate_found:
                break
            next_limit = query_limit * 2
            if maximum_candidates is not None:
                next_limit = min(next_limit, maximum_candidates)
            if next_limit == query_limit:
                break
            query_limit = next_limit

        if not sources:
            return "No relevant documents found.", []

        context = "\n\n".join(context_parts)
        prompt = f"""Given the following context from research papers, answer the question.
If the answer is not in the context, state that.
Context:

{context}

Question: {question}"""
        profile = llm_profile or {}
        if investigation_plan:
            prompt_sources = tuple(SourceReference.model_validate(source) for source in sources)
            normalized_question = normalize_investigation_question(question)
            prompt = build_investigation_plan_prompt(normalized_question, context, prompt_sources)
            profile = dict(profile)
            chat_options = dict(profile.get("chat_options", {}))
            chat_options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "investigation_plan",
                    "strict": True,
                    "schema": investigation_plan_schema(),
                },
            }
            profile["chat_options"] = chat_options
        llm_response = self.llm_client.complete(
            prompt=prompt,
            profile=profile,
            model=llm_model,
        )
        if investigation_plan:
            plan = parse_investigation_plan_json(
                llm_response.text,
                InvestigationPlanValidationContext(
                    expected_question=question,
                    allowed_source_ids=frozenset(source["paper_id"] for source in sources),
                    allowed_execution_evidence_refs=frozenset(),
                ),
            )
            return render_investigation_plan_markdown(plan), sources
        return llm_response.text, sources
