# tests/app/use_cases/test_synthesis.py

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Assuming these will be defined in src/papers/app/use_cases/synthesis.py
# For now, we'll create a simple placeholder Callable for testing purposes
from papers.app.ports import (
    BlobStore,
    Embedder,
    LLMClient,
    LLMResponse,
    PaperProjectStore,
    PaperStore,
    VectorIndex,
)
from papers.app.use_cases.synthesis import SynthesizeFromCorpusUseCase

# --- Fake Implementations of Protocols ---


@dataclass
class FakeEmbedder(Embedder):
    embedding_dimension: int = 768
    model_name_str: str = "mock-embedder"

    def model_name(self) -> str:
        return self.model_name_str

    def dimension(self) -> int:
        return self.embedding_dimension

    def embed(self, text: str) -> list[float]:
        # Return a dummy embedding based on text hash for deterministic tests
        embedding_base = [float(ord(c)) for c in text[: self.embedding_dimension]]
        if len(text) < self.embedding_dimension:
            return embedding_base + [0.0] * (self.embedding_dimension - len(text))
        else:
            return embedding_base


@dataclass
class FakeVectorIndex(VectorIndex):
    store: dict[str, list[float]] = field(default_factory=dict)
    query_results: list[tuple[str, float]] = field(default_factory=list)
    last_allowed_ids: set[str] | None = None

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        self.store[paper_id] = embedding

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        self.last_allowed_ids = allowed_ids
        results = self.query_results
        if allowed_ids is not None:
            results = [result for result in results if result[0] in allowed_ids]
        return results[:limit]


@dataclass
class FakePaperStore(PaperStore):
    papers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_paper(self, fields: dict[str, Any]) -> str:
        paper_id = fields["paper_id"]
        self.papers[paper_id] = dict(fields)
        return paper_id

    def get(self, paper_id: str) -> dict[str, Any] | None:
        return self.papers.get(paper_id)

    # Implement other PaperStore methods if needed by the use case
    def update_metadata(self, paper_id: str, fields: dict[str, Any]) -> None:
        pass

    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None:
        pass

    def set_markdown_provenance(
        self,
        paper_id: str,
        md_xxh64: str,
        src_pdf_xxh64: str,
        converter: str,
        converter_version: str,
    ) -> None:
        pass

    def set_embedding_state(
        self,
        paper_id: str,
        embedding_model: str,
        embedding_dimension: int,
        text_slice_strategy: str,
        embedded_from_md_xxh64: str,
    ) -> None:
        pass

    def advance_pipeline_stage_monotonic(self, paper_id: str, new_stage: str) -> None:
        pass

    def set_pipeline_health_error(
        self, paper_id: str, error_code: str, message: str, job_id: str | None
    ) -> None:
        pass

    def clear_pipeline_health_if_recovered(self, paper_id: str, job_type: str) -> None:
        pass

    def list_papers_with_markdown(self) -> list[str]:
        return list(self.papers.keys())  # Simplified

    def delete_paper(self, paper_id: str) -> None:
        pass

    def reset_pipeline_stage(self, paper_id: str, stage: str) -> None:
        pass


@dataclass
class FakeBlobStore(BlobStore):
    markdown_content: dict[str, str] = field(default_factory=dict)

    # Simulate pathlib.Path by returning a mock object with read_text
    class MockPath:
        def __init__(self, content: str, exists: bool = True):
            self._content = content
            self._exists = exists

        def read_text(self) -> str:
            return self._content

        def exists(self) -> bool:
            return self._exists

    def get_markdown_path(self, paper_id: str) -> Any | None:
        content = self.markdown_content.get(paper_id)
        return self.MockPath(content, exists=bool(content)) if content else None

    # Implement other BlobStore methods if needed by the use case
    def put_pdf(self, src_path: Path) -> tuple[str, Path]:
        return "fake_xxh64", src_path

    def get_pdf_path(self, pdf_xxh64: str) -> Path | None:
        return None

    def put_markdown(self, paper_id: str, markdown: str) -> tuple[Path, str]:
        return Path("/mock/path"), "fake_md_xxh64"

    def put_analysis_artifacts(
        self, run_id: str, output_md: str, output_json: dict | None, meta_json: dict
    ) -> dict[str, Path]:
        return {}


@dataclass
class FakeLLMClient(LLMClient):
    response_text: str = "Mocked LLM response."
    mock_llm_exception: type[Exception] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse:
        self.calls.append({"prompt": prompt, "profile": profile, "model": model})
        if self.mock_llm_exception:
            raise self.mock_llm_exception("LLM Mock Error")
        return LLMResponse(text=self.response_text, tokens_in=100, tokens_out=50, cost_usd=0.01)


@dataclass
class FakePaperProjectStore(PaperProjectStore):
    project_papers: dict[str, list[str]] = field(default_factory=dict)

    def list_paper_ids(self, project_id: str, label: str | None = None) -> list[str]:
        return self.project_papers.get(project_id, [])

    # Implement other PaperProjectStore methods if needed by the use case
    def is_attached(self, paper_id: str, project_id: str) -> bool:
        return False

    def attach(self, paper_id: str, project_id: str, label: str | None = None) -> None:
        pass


# --- Test Cases for SynthesizeFromCorpusUseCase ---


class TestSynthesizeFromCorpusUseCase:
    question = "What are the common challenges in stochastic optimization?"
    project_id = "proj-123"
    paper_ids = ["paper-1", "paper-2", "paper-3"]
    llm_answer = "Based on the provided papers, common challenges include..."

    @pytest.fixture
    def setup_mocks(self):
        embedder = FakeEmbedder()
        vector_index = FakeVectorIndex(
            query_results=[(pid, 0.9 - i * 0.1) for i, pid in enumerate(self.paper_ids)]
        )
        paper_store = FakePaperStore()
        blob_store = FakeBlobStore()
        llm_client = FakeLLMClient(response_text=self.llm_answer)
        paper_project_store = FakePaperProjectStore()

        # Populate stores with dummy data
        for i, pid in enumerate(self.paper_ids):
            paper_store.create_paper(
                {"paper_id": pid, "title": f"Paper {i + 1} on Stochastic Optimization"}
            )
            blob_store.markdown_content[pid] = f"This is the content of Paper {i + 1}."

        paper_project_store.project_papers[self.project_id] = self.paper_ids[
            :2
        ]  # Simulate only paper-1 and paper-2 in project

        return {
            "embedder": embedder,
            "vector_index": vector_index,
            "paper_store": paper_store,
            "blob_store": blob_store,
            "llm_client": llm_client,
            "paper_project_store": paper_project_store,
        }

    def test_synthesis_use_case_returns_answer_and_sources_happy_path(self, setup_mocks):
        """
        Tests verify a user's question is correctly embedded and used for hybrid search.
        Tests verify that retrieved content is correctly assembled into a context block for the LLM.
        Tests verify the LLM is called with a correctly formatted prompt
        containing the context and question.
        Tests verify the use case returns both a generated answer and a list of source paper IDs.
        """
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)
        answer, sources = use_case.synthesize(self.question)

        # Verify LLM was called
        assert len(setup_mocks["llm_client"].calls) == 1
        llm_call = setup_mocks["llm_client"].calls[0]
        assert self.question in llm_call["prompt"]
        assert "This is the content of Paper 1." in llm_call["prompt"]
        assert "This is the content of Paper 2." in llm_call["prompt"]
        assert "This is the content of Paper 3." in llm_call["prompt"]

        # Verify output
        assert answer == self.llm_answer
        assert len(sources) == len(self.paper_ids)
        assert {s["paper_id"] for s in sources} == set(self.paper_ids)
        assert {s["title"] for s in sources} == {
            "Paper 1 on Stochastic Optimization",
            "Paper 2 on Stochastic Optimization",
            "Paper 3 on Stochastic Optimization",
        }

    def test_synthesis_use_case_honors_project_scope(self, setup_mocks):
        """
        Tests verify that scoping by project correctly limits the document search space.
        """
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)
        answer, sources = use_case.synthesize(self.question, project_id=self.project_id)

        # Verify LLM was called with context only from papers in the project
        assert len(setup_mocks["llm_client"].calls) == 1
        llm_call = setup_mocks["llm_client"].calls[0]
        assert "This is the content of Paper 1." in llm_call["prompt"]
        assert "This is the content of Paper 2." in llm_call["prompt"]
        assert "This is the content of Paper 3." not in llm_call["prompt"]  # Paper 3 not in project

        # Verify output sources are only from the project
        assert answer == self.llm_answer
        assert len(sources) == 2  # Only paper-1 and paper-2 in project
        assert {s["paper_id"] for s in sources} == {"paper-1", "paper-2"}

    def test_project_scope_filters_before_top_n(self, setup_mocks):
        setup_mocks["vector_index"].query_results = [
            ("global-1", 0.99),
            ("global-2", 0.98),
            ("paper-1", 0.97),
        ]
        setup_mocks["paper_project_store"].project_papers[self.project_id] = ["paper-1"]
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        _answer, sources = use_case.synthesize(
            self.question,
            project_id=self.project_id,
            num_retrieved_docs=2,
        )

        assert setup_mocks["vector_index"].last_allowed_ids == {"paper-1"}
        assert [source["paper_id"] for source in sources] == ["paper-1"]

    def test_default_profile_preserves_client_configuration(self, setup_mocks):
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        use_case.synthesize(self.question)

        assert setup_mocks["llm_client"].calls[0]["profile"] == {}

    def test_project_scope_requires_project_store(self, setup_mocks):
        setup_mocks["paper_project_store"] = None
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        with pytest.raises(ValueError, match="project scoping is not configured"):
            use_case.synthesize(self.question, project_id=self.project_id)

    def test_synthesis_skips_missing_paper_or_markdown(self, setup_mocks):
        setup_mocks["vector_index"].query_results = [("missing", 1.0), ("paper-1", 0.9)]
        setup_mocks["blob_store"].markdown_content.pop("paper-1")
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        answer, sources = use_case.synthesize(self.question)

        assert answer == "No relevant documents found."
        assert sources == []
        assert setup_mocks["llm_client"].calls == []

    def test_synthesis_backfills_unusable_top_hits(self, setup_mocks):
        setup_mocks["vector_index"].query_results = [
            ("missing-1", 1.0),
            ("missing-2", 0.9),
            ("paper-1", 0.8),
            ("paper-2", 0.7),
        ]
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        _answer, sources = use_case.synthesize(self.question, num_retrieved_docs=2)

        assert [source["paper_id"] for source in sources] == ["paper-1", "paper-2"]

    def test_synthesis_uses_untitled_for_missing_title(self, setup_mocks):
        setup_mocks["paper_store"].papers["paper-1"].pop("title")
        setup_mocks["vector_index"].query_results = [("paper-1", 1.0)]
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        _answer, sources = use_case.synthesize(self.question)

        assert sources == [{"paper_id": "paper-1", "title": "Untitled"}]

    def test_synthesis_use_case_handles_no_retrieved_documents(self, setup_mocks):
        """
        Tests verify the use case handles cases with no retrieved documents.
        """
        setup_mocks["vector_index"].query_results = []  # No documents retrieved
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)
        answer, sources = use_case.synthesize(self.question)

        assert "No relevant documents found." in answer
        assert sources == []
        assert len(setup_mocks["llm_client"].calls) == 0  # LLM should not be called

    def test_synthesis_use_case_handles_llm_error(self, setup_mocks):
        """
        Tests verify the use case handles LLM errors gracefully.
        """
        setup_mocks["llm_client"].mock_llm_exception = ValueError
        use_case = SynthesizeFromCorpusUseCase(**setup_mocks)

        with pytest.raises(ValueError, match="LLM Mock Error"):
            use_case.synthesize(self.question)

        assert len(setup_mocks["llm_client"].calls) == 1  # LLM was called before error
