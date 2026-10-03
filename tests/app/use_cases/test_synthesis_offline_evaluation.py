from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter

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


class ClaimFixture(BaseModel):
    text: str
    paper: int


class EvaluationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    question: str
    papers: list[str]
    status: str
    claims: list[ClaimFixture]
    limitations: list[str]
    tamper: str | None = None


CASES = TypeAdapter(list[EvaluationFixture]).validate_json(
    (Path(__file__).parents[2] / "fixtures/synthesis/offline-evaluation.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_offline_grounding_evaluation(case: EvaluationFixture) -> None:
    papers = FakePaperStore()
    blobs = FakeBlobStore()
    ids = [f"paper-{index}" for index in range(len(case.papers))]
    for paper_id, content in zip(ids, case.papers, strict=True):
        papers.papers[paper_id] = {"paper_id": paper_id, "title": paper_id}
        blobs.markdown_content[paper_id] = content
    projects = FakePaperProjectStore(project_papers={"evaluation": ids})
    index = FakeVectorIndex(query_results=[(paper_id, 1.0) for paper_id in ids])
    embedder = FakeEmbedder()
    refs = SynthesisRetrieval(embedder, index, papers, blobs, projects).retrieve(
        case.question, "evaluation", 5
    )
    claims = []
    for claim in case.claims:
        reference = refs[claim.paper].model_dump()
        if case.tamper:
            reference["quote"] = "Invented support."
        claims.append({"text": claim.text, "references": [reference]})
    llm = FakeLLMClient(
        response_text=json.dumps(
            {"status": case.status, "claims": claims, "limitations": case.limitations}
        )
    )
    use_case = SynthesizeFromCorpusUseCase(embedder, index, papers, blobs, llm, projects)
    if case.tamper:
        with pytest.raises(ValueError):
            use_case.synthesize_grounded(case.question, "evaluation")
    else:
        answer = use_case.synthesize_grounded(case.question, "evaluation")
        assert answer.status == case.status
        assert len(answer.claims) == len(case.claims)
        assert all(source.paper_id in ids for source in answer.sources)
