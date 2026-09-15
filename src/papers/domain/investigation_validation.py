from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError as PydanticValidationError

from papers.domain.errors import OutputValidationFailed
from papers.domain.investigation_evidence import StepStatus
from papers.domain.investigation_plan import InvestigationPlan
from papers.domain.policies import parse_structured_json


@dataclass(frozen=True, slots=True)
class InvestigationPlanValidationContext:
    expected_question: str
    allowed_source_ids: frozenset[str]
    allowed_execution_evidence_refs: frozenset[str]


def normalize_investigation_question(question: str) -> str:
    return " ".join(question.split())


def parse_investigation_plan_json(
    payload: str,
    context: InvestigationPlanValidationContext | None = None,
) -> InvestigationPlan:
    data = parse_structured_json(payload)
    try:
        plan = InvestigationPlan.model_validate(data)
    except PydanticValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']} ({error['msg']})"
            for error in exc.errors(include_input=False)
        )
        raise OutputValidationFailed(f"investigation plan failed validation: {summary}") from exc
    if context is None:
        return plan
    expected_question = normalize_investigation_question(context.expected_question)
    if normalize_investigation_question(plan.question).casefold() != expected_question.casefold():
        raise OutputValidationFailed("investigation plan question does not match request")
    returned_ids = {source.paper_id for source in plan.sources}
    if not returned_ids.issubset(context.allowed_source_ids):
        raise OutputValidationFailed("investigation plan cited sources outside retrieved corpus")
    execution_refs = _collect_execution_evidence_refs(plan)
    if not execution_refs.issubset(context.allowed_execution_evidence_refs):
        raise OutputValidationFailed(
            "investigation plan claimed verification without supplied execution evidence"
        )
    return plan.model_copy(update={"question": expected_question})


def _collect_execution_evidence_refs(plan: InvestigationPlan) -> set[str]:
    refs = {
        ref
        for step in plan.baseline_replication.steps
        if step.status is StepStatus.verified
        for ref in step.evidence_refs
    }
    refs.update(
        ref
        for direction in plan.directions
        for step in direction.replication_steps
        if step.status is StepStatus.verified
        for ref in step.evidence_refs
    )
    return refs
