from __future__ import annotations

from papers.app.use_cases.synthesis import SynthesizeFromCorpusUseCase
from papers.app.use_cases.synthesis_sources import SynthesisRetrieval
from tests.app.use_cases.test_synthesis import (
    FakeBlobStore,
    FakeEmbedder,
    FakeLLMClient,
    FakePaperProjectStore,
    FakePaperStore,
    FakeVectorIndex,
)


def test_empty_project_never_calls_llm_or_uses_other_papers() -> None:
    llm = FakeLLMClient()
    index = FakeVectorIndex(query_results=[("outside", 1.0)])
    use_case = SynthesizeFromCorpusUseCase(
        FakeEmbedder(), index, FakePaperStore(), FakeBlobStore(), llm, FakePaperProjectStore()
    )
    answer = use_case.synthesize_grounded("Does treatment help?", project_id="empty")
    assert answer.status == "insufficient"
    assert not answer.sources
    assert not llm.calls
    assert index.last_allowed_ids is None


class LeakingIndex(FakeVectorIndex):
    def query(
        self, embedding: list[float], limit: int, *, allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        return [("outside", 1.0), ("inside", 0.8)][:limit]


def test_scope_guard_rejects_outside_results_from_faulty_provider() -> None:
    papers = FakePaperStore(
        papers={"outside": {"title": "Excluded"}, "inside": {"title": "Included"}}
    )
    blobs = FakeBlobStore(
        markdown_content={"outside": "Secret material.", "inside": "# Results\r\nCafé improves."}
    )
    projects = FakePaperProjectStore(project_papers={"selected": ["inside"]})
    refs = SynthesisRetrieval(FakeEmbedder(), LeakingIndex(), papers, blobs, projects).retrieve(
        "Results?", "selected", 5
    )
    assert all(ref.paper_id == "inside" for ref in refs)
    # A misbehaving top-N provider cannot cause outside evidence to leak.
    assert not refs


def test_utf8_crlf_locators_bind_exact_markdown_bytes() -> None:
    text = "# Results\r\nCafé improves."
    refs = SynthesisRetrieval(
        FakeEmbedder(),
        FakeVectorIndex(query_results=[("p", 1.0)]),
        FakePaperStore(papers={"p": {"title": "Unicode"}}),
        FakeBlobStore(markdown_content={"p": text}),
        None,
    ).retrieve("What?", None, 1)
    from papers.domain.synthesis_grounding import verify_source

    assert len(refs) == 1
    assert verify_source(refs[0], text.encode()) == "valid"
    assert text.encode()[refs[0].byte_start : refs[0].byte_end].decode() == refs[0].quote


def test_investigation_retains_full_markdown_context(tmp_path) -> None:
    import json

    from papers.infra.blobs_fs.store import FileSystemBlobStore
    from tests.investigation_plan_test_data import valid_investigation_plan_payload

    blobs = FileSystemBlobStore(tmp_path)
    text = "# Results\n" + "Recorded evidence. " * 500
    blobs.put_markdown("paper-1", text)
    llm = FakeLLMClient(response_text=json.dumps(valid_investigation_plan_payload("What?")))
    use_case = SynthesizeFromCorpusUseCase(
        FakeEmbedder(),
        FakeVectorIndex(query_results=[("paper-1", 1.0)]),
        FakePaperStore(papers={"paper-1": {"title": "Trial"}}),
        blobs,
        llm,
    )
    answer, sources = use_case.synthesize("What?", investigation_plan=True)
    assert sources == [{"paper_id": "paper-1", "title": "Trial"}]
    assert text in llm.calls[0]["prompt"]
    assert answer


def test_retrieval_skips_unreadable_and_blank_artifacts(tmp_path) -> None:
    from papers.infra.blobs_fs.store import FileSystemBlobStore

    blobs = FileSystemBlobStore(tmp_path)
    ids = ["invalid", "directory", "empty", "paper-1"]
    for paper_id in ids:
        blobs.put_markdown(paper_id, "# Results\nReadable evidence.")
    (tmp_path / "md/invalid.md").write_bytes(b"\xff")
    (tmp_path / "md/directory.md").unlink()
    (tmp_path / "md/directory.md").mkdir()
    (tmp_path / "md/empty.md").write_bytes(b"# Blank\n")
    index = FakeVectorIndex(query_results=[(paper_id, 1.0) for paper_id in ids])
    papers = FakePaperStore(papers={paper_id: {"title": paper_id} for paper_id in ids})
    refs = SynthesisRetrieval(FakeEmbedder(), index, papers, blobs, None).retrieve("What?", None, 1)
    assert [ref.paper_id for ref in refs] == ["paper-1"]


def test_empty_investigation_preserves_legacy_tuple() -> None:
    uc = SynthesizeFromCorpusUseCase(
        FakeEmbedder(), FakeVectorIndex(), FakePaperStore(), FakeBlobStore(), FakeLLMClient()
    )
    assert uc.synthesize("What?", investigation_plan=True) == ("No relevant documents found.", [])


def test_plain_uncited_model_answer_is_rejected() -> None:
    import pytest

    from tests.api.papers.fakes import LLM

    llm = LLM()
    llm.responses.append("The treatment improves lifetime survival.")
    uc = SynthesizeFromCorpusUseCase(
        FakeEmbedder(),
        FakeVectorIndex(query_results=[("paper-1", 1.0)]),
        FakePaperStore(papers={"paper-1": {"title": "Accuracy study"}}),
        FakeBlobStore(markdown_content={"paper-1": "Short-term accuracy improved."}),
        llm,
    )
    with pytest.raises(ValueError):
        uc.synthesize("Does it improve lifetime survival?")
