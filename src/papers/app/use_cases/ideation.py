from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from papers.app.ideation_contracts import (
    IdeateProjectRequest,
    IdeationInputError,
    PlanIdeaRequest,
    StructuredOutputOptions,
    critique_schema,
    generation_schema,
    investigation_schema,
    structured_profile,
)
from papers.app.ports import BlobStore, LLMClient, PaperProjectStore, PaperStore, ProjectStore
from papers.domain.errors import NotFoundError
from papers.domain.ideation_artifacts import IdeationBundleData, write_ideation_bundle
from papers.domain.ideation_bundle import (
    PLAN_ARTIFACTS,
    BundleType,
    JsonValue,
    atomic_bundle,
    verify_manifest,
    write_json,
    write_manifest,
)
from papers.domain.ideation_evidence import build_evidence_map
from papers.domain.ideation_frozen import load_frozen_ideation_inputs
from papers.domain.ideation_prompt import build_critique_prompt, build_generation_prompt
from papers.domain.ideation_validation import (
    IdeationValidationContext,
    parse_critique_json,
    parse_generation_json,
)
from papers.domain.investigation_evidence import SourceReference
from papers.domain.investigation_prompt import build_investigation_plan_prompt
from papers.domain.investigation_renderer import render_investigation_plan_markdown
from papers.domain.investigation_validation import (
    InvestigationPlanValidationContext,
    parse_investigation_plan_json,
)


@dataclass(frozen=True, slots=True)
class IdeateProjectUseCase:
    project_store: ProjectStore
    paper_project_store: PaperProjectStore
    paper_store: PaperStore
    blob_store: BlobStore
    llm_client: LLMClient
    repo_root: Path

    def run(self, request: IdeateProjectRequest) -> Path:
        project = self.project_store.get(request.project_id)
        if project is None:
            raise NotFoundError(f"project not found: {request.project_id}")
        paper_ids = self.paper_project_store.list_paper_ids(request.project_id)
        if len(paper_ids) > request.max_papers:
            raise IdeationInputError(
                f"project {request.project_id} contains {len(paper_ids)} papers; "
                f"maximum is {request.max_papers}"
            )
        papers: dict[str, tuple[str, Path | None]] = {}
        for paper_id in paper_ids:
            paper = self.paper_store.get(paper_id)
            if paper is None:
                raise NotFoundError(f"paper not found: {paper_id}")
            papers[paper_id] = (
                str(paper.get("title") or "Untitled"),
                self.blob_store.get_markdown_path(paper_id),
            )
        evidence = build_evidence_map(
            request.project_id,
            str(project.get("name") or request.project_id),
            paper_ids,
            papers,
            excerpt_bytes=request.excerpt_bytes,
            max_excerpts_per_paper=request.max_excerpts_per_paper,
        )
        if not evidence.excerpts:
            raise IdeationInputError("project has no readable Markdown excerpts")
        generation_response = self.llm_client.complete(
            prompt=build_generation_prompt(request.question, evidence),
            profile=structured_profile(
                request.profile,
                StructuredOutputOptions(
                    "project_ideation",
                    generation_schema(sorted(excerpt.excerpt_id for excerpt in evidence.excerpts)),
                    request.max_tokens,
                ),
            ),
            model=request.model,
            timeout_s=request.timeout_s,
        )
        generation = parse_generation_json(
            generation_response.text,
            IdeationValidationContext(
                expected_question=request.question,
                allowed_excerpt_ids=frozenset(excerpt.excerpt_id for excerpt in evidence.excerpts),
            ),
        )
        critique_response = self.llm_client.complete(
            prompt=build_critique_prompt(generation, evidence),
            profile=structured_profile(
                request.profile,
                StructuredOutputOptions(
                    "project_ideation_critique",
                    critique_schema(sorted(excerpt.excerpt_id for excerpt in evidence.excerpts)),
                    request.max_tokens,
                ),
            ),
            model=request.critic_model or request.model,
            timeout_s=request.timeout_s,
        )
        critique = parse_critique_json(
            critique_response.text,
            frozenset(idea.idea_id for idea in generation.ideas),
            frozenset(excerpt.excerpt_id for excerpt in evidence.excerpts),
        )
        return write_ideation_bundle(
            self.repo_root,
            IdeationBundleData(
                evidence=evidence,
                generation=generation,
                critique=critique,
                generation_model=request.model,
                critic_model=request.critic_model or request.model,
            ),
        )


@dataclass(frozen=True, slots=True)
class PlanIdeaUseCase:
    llm_client: LLMClient
    repo_root: Path

    def run(self, request: PlanIdeaRequest) -> Path:
        source_hashes = verify_manifest(request.bundle, BundleType.project_ideation)
        evidence, generation = load_frozen_ideation_inputs(request.bundle, source_hashes)
        ideas = {idea.idea_id: idea for idea in generation.ideas}
        idea = ideas.get(request.idea_id)
        if idea is None:
            raise NotFoundError(f"idea not found in bundle: {request.idea_id}")
        cited = [
            excerpt
            for excerpt in evidence.excerpts
            if excerpt.excerpt_id in set(idea.citation_excerpt_ids)
        ]
        source_ids = tuple(dict.fromkeys(excerpt.paper_id for excerpt in cited))
        sources = tuple(
            SourceReference(
                paper_id=paper_id,
                title=next(excerpt.title for excerpt in cited if excerpt.paper_id == paper_id),
            )
            for paper_id in source_ids
        )
        excerpt_context = "\n\n".join(
            f"Excerpt ID: {excerpt.excerpt_id}\nPaper ID: {excerpt.paper_id}\n"
            f"Section: {excerpt.section}\nExact quote: {excerpt.quote}"
            for excerpt in cited
        )
        context = (
            "Selected draft idea (proposal, not paper evidence):\n"
            f"{idea.model_dump_json(indent=2)}\n\nFrozen cited excerpts:\n{excerpt_context}"
        )
        prompt = build_investigation_plan_prompt(idea.falsifiable_question, context, sources)
        prompt += """

Local structured-output guidance: include at least one direction. Treat the selected draft idea as
proposed, never reported. Unless an exact quote supports a requirement, represent it as proposed
with a concrete value, basis/rationale, and empty source_refs, or as unknown. Canonical unknown
EvidenceStatement: claim_kind=inference, evidence_status=unknown, value=null, source_refs=[], and a
non-null uncertainty_rationale. Canonical unknown NumericEstimate: claim_kind=inference,
evidence_status=unknown, value=null, unit is still a non-empty unit label, basis=null,
source_refs=[], and a non-null uncertainty_rationale. Canonical unknown InformationCompleteness:
evidence_status=unknown, assessment=null, source_refs=[], and a non-null uncertainty_rationale.
Every assumption must use either that canonical unknown EvidenceStatement or claim_kind=proposal,
evidence_status=proposed, a non-null value, source_refs=[], and a non-null uncertainty_rationale.
For replication steps, not_started and verified require blocked_reason=null; blocked requires a
non-null blocked_reason; verified also requires at least one execution evidence_refs value.
Use decimal JSON numbers such as 8.0, not integers, for any proposed numeric estimate."""
        response = self.llm_client.complete(
            prompt=prompt,
            profile=structured_profile(
                request.profile,
                StructuredOutputOptions(
                    "selected_idea_plan",
                    investigation_schema(sorted(source_ids)),
                    request.max_tokens,
                ),
            ),
            model=request.model,
            timeout_s=request.timeout_s,
        )
        plan = parse_investigation_plan_json(
            response.text,
            InvestigationPlanValidationContext(
                expected_question=idea.falsifiable_question,
                allowed_source_ids=frozenset(source_ids),
                allowed_execution_evidence_refs=frozenset(),
            ),
        )
        source_manifest: dict[str, JsonValue] = {
            name: digest for name, digest in source_hashes.items()
        }
        provenance: JsonValue = {
            "created_at": datetime.now(UTC).isoformat(),
            "source_bundle": str(request.bundle.resolve()),
            "source_manifest": source_manifest,
            "idea_id": request.idea_id,
            "selection_note": request.selection_note,
            "model": request.model,
            "retrieval_performed": False,
            "human_approval_claimed": False,
        }
        with atomic_bundle(self.repo_root, "selected-idea-plan") as (staging, published):
            write_json(staging / "investigation-plan.json", plan.model_dump(mode="json"))
            (staging / "report.md").write_text(render_investigation_plan_markdown(plan) + "\n")
            write_json(staging / "provenance.json", provenance)
            write_manifest(staging, PLAN_ARTIFACTS)
        return published
