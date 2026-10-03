from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, OperationError, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.profiles import llm_profile
from gleansight.api.runtime import ApiRuntime
from papers.app.ideation_contracts import IdeateProjectRequest, PlanIdeaRequest
from papers.app.use_cases.ideation import IdeateProjectUseCase, PlanIdeaUseCase
from papers.app.use_cases.synthesis import SynthesizeFromCorpusUseCase


class ModelSelection(Request):
    profile_id: Identifier | None = None
    model: Identifier | None = None


class Ask(ModelSelection):
    question: Identifier
    project_id: Identifier | None = None
    num_retrieved_docs: Annotated[int, Field(ge=1, le=100)] = 5
    investigation_plan: bool = False


class ResearchOptions(ModelSelection):
    timeout_s: Annotated[int, Field(ge=1, le=600)] = 300
    max_tokens: Annotated[int, Field(ge=256)] = 8000


class Ideate(ResearchOptions):
    project_id: Identifier
    question: Identifier
    critic_model: Identifier | None = None
    max_papers: Annotated[int, Field(ge=1)] = 12
    excerpt_bytes: Annotated[int, Field(ge=200)] = 1200
    max_excerpts_per_paper: Annotated[int, Field(ge=1, le=12)] = 6


class PlanIdea(ResearchOptions):
    bundle_path: Path
    idea_id: Identifier
    selection_note: Identifier


def ask(runtime: ApiRuntime, request: Ask) -> JsonValue:
    profile = llm_profile(runtime, request.profile_id)
    base = runtime.papers
    use_case = SynthesizeFromCorpusUseCase(
        embedder=base.embedder,
        vector_index=base.vector_index,
        paper_store=base.paper_store,
        blob_store=base.blob_store,
        llm_client=base.llm_client,
        paper_project_store=base.paper_project_store,
    )
    if not request.investigation_plan:
        grounded = use_case.synthesize_grounded(
            question=request.question,
            project_id=request.project_id,
            num_retrieved_docs=request.num_retrieved_docs,
            llm_profile=profile,
            llm_model=request.model or runtime.settings.llm.default_model,
        )
        return json_result(
            {
                "answer": grounded.render(),
                "sources": [source.model_dump() for source in grounded.sources],
                "grounding": grounded.model_dump(),
            }
        )
    result, sources = use_case.synthesize(
        question=request.question,
        project_id=request.project_id,
        num_retrieved_docs=request.num_retrieved_docs,
        llm_profile=profile,
        llm_model=request.model or runtime.settings.llm.default_model,
        investigation_plan=request.investigation_plan,
    )
    return json_result({"answer": result, "sources": sources})


def ideate(runtime: ApiRuntime, request: Ideate) -> JsonValue:
    profile = llm_profile(runtime, request.profile_id)
    base = runtime.papers
    bundle = IdeateProjectUseCase(
        project_store=base.project_store,
        paper_project_store=base.paper_project_store,
        paper_store=base.paper_store,
        blob_store=base.blob_store,
        llm_client=base.llm_client,
        repo_root=runtime.repo_root,
    ).run(
        IdeateProjectRequest(
            project_id=request.project_id,
            question=request.question,
            profile=profile,
            model=request.model or runtime.settings.llm.default_model,
            critic_model=request.critic_model,
            max_papers=request.max_papers,
            excerpt_bytes=request.excerpt_bytes,
            max_excerpts_per_paper=request.max_excerpts_per_paper,
            timeout_s=request.timeout_s,
            max_tokens=request.max_tokens,
        )
    )
    return {"bundle": str(bundle)}


def plan_idea(runtime: ApiRuntime, request: PlanIdea) -> JsonValue:
    bundle = runtime.resolve(request.bundle_path)
    if not bundle.is_relative_to((runtime.repo_root / "output").resolve()) or not bundle.is_dir():
        raise OperationError(
            "invalid_path", "Idea bundle must be an existing directory under output/."
        )
    profile = llm_profile(runtime, request.profile_id)
    result = PlanIdeaUseCase(runtime.papers.llm_client, runtime.repo_root).run(
        PlanIdeaRequest(
            bundle=bundle,
            idea_id=request.idea_id,
            profile=profile,
            model=request.model or runtime.settings.llm.default_model,
            timeout_s=request.timeout_s,
            max_tokens=request.max_tokens,
            selection_note=request.selection_note,
        )
    )
    return {"bundle": str(result)}


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.synthesis.ask",
            "Answer a question from readable corpus evidence.",
            Ask,
            ask,
            ("read", "external"),
        ),
        Operation(
            "papers.research.ideate-project",
            "Generate an evidence-grounded ideation report bundle.",
            Ideate,
            ideate,
            ("write", "external"),
        ),
        Operation(
            "papers.research.plan-idea",
            "Plan a selected idea from a verified report bundle.",
            PlanIdea,
            plan_idea,
            ("write", "external"),
        ),
    )
