from __future__ import annotations

from enum import StrEnum
from typing import Final, Self, assert_never

from pydantic import Field, field_validator, model_validator

from papers.domain.investigation_evidence import (
    ClaimKind,
    CompletenessAssessment,
    CompletionStr,
    ComputeFeasibilityTier,
    ComputeRequirements,
    ContractModel,
    ContractValueError,
    DataRequirements,
    EvidenceStatement,
    EvidenceStatus,
    InformationCompleteness,
    ModelRequirements,
    NonEmptyStr,
    NumericEstimate,
    ReplicationStep,
    SourceReference,
    StepStatus,
)

__all__ = [
    "BaselineReplication",
    "ClaimKind",
    "ComparisonScope",
    "CompletenessAssessment",
    "ComputeFeasibilityTier",
    "ComputeRequirements",
    "DataRequirements",
    "EvidenceStatement",
    "EvidenceStatus",
    "InformationCompleteness",
    "InvestigationDirection",
    "InvestigationPlan",
    "ModelRequirements",
    "NumericEstimate",
    "ReplicationStep",
    "ReplicationStrategy",
    "SourceReference",
    "StepStatus",
]

_NO_MISSING_INFORMATION_SENTINELS: Final = frozenset({"no missing information", "none identified"})


class ReplicationStrategy(StrEnum):
    exact_replication = "exact_replication"
    constrained_reproduction = "constrained_reproduction"
    conceptual_reimplementation = "conceptual_reimplementation"


class ComparisonScope(StrEnum):
    direct_metrics = "direct_metrics"
    mechanism_only = "mechanism_only"
    no_direct_comparison = "no_direct_comparison"


class BaselineReplication(ContractModel):
    core_paper_ref: CompletionStr
    strategy: ReplicationStrategy = Field(
        description=(
            "exact_replication targets the original protocol without substitutions; "
            "constrained_reproduction records every substitution; conceptual_reimplementation "
            "tests only the mechanism and forbids direct metric comparison"
        )
    )
    justification: CompletionStr
    missing_information: tuple[CompletionStr, ...]
    information_completeness: InformationCompleteness
    protocol_equivalence: EvidenceStatement
    metric_comparability: EvidenceStatement
    deviations: tuple[EvidenceStatement, ...]
    comparison_scope: ComparisonScope
    success_criteria: tuple[CompletionStr, ...] = Field(min_length=1)
    stop_advance_rule: CompletionStr
    steps: tuple[ReplicationStep, ...] = Field(min_length=1)

    @field_validator("missing_information")
    @classmethod
    def reject_no_information_sentinels(
        cls,
        value: tuple[CompletionStr, ...],
    ) -> tuple[CompletionStr, ...]:
        if any(
            " ".join(item.split()).casefold() in _NO_MISSING_INFORMATION_SENTINELS for item in value
        ):
            raise ContractValueError(
                "no-information sentinels must use an empty missing-information inventory"
            )
        return value

    @model_validator(mode="after")
    def validate_replication_semantics(self) -> Self:
        self._validate_information_inventory()
        has_concrete_deviations = bool(self.deviations) and all(
            deviation.evidence_status in {EvidenceStatus.reported, EvidenceStatus.proposed}
            and deviation.value is not None
            for deviation in self.deviations
        )
        match self.strategy:
            case ReplicationStrategy.exact_replication:
                if self.deviations:
                    raise ContractValueError("exact replication cannot contain planned deviations")
                if self.comparison_scope is ComparisonScope.mechanism_only:
                    raise ContractValueError("exact replication is not a mechanism-only comparison")
                if self.comparison_scope is ComparisonScope.direct_metrics:
                    if (
                        self.protocol_equivalence.evidence_status is not EvidenceStatus.reported
                        or self.metric_comparability.evidence_status is not EvidenceStatus.reported
                        or self.protocol_equivalence.claim_kind is not ClaimKind.fact
                        or self.metric_comparability.claim_kind is not ClaimKind.fact
                    ):
                        raise ContractValueError(
                            "exact direct metrics require reported protocol equivalence "
                            "and comparability"
                        )
            case ReplicationStrategy.constrained_reproduction:
                if not has_concrete_deviations:
                    raise ContractValueError(
                        "constrained reproduction requires concrete named substitutions"
                    )
                if (
                    self.comparison_scope is ComparisonScope.direct_metrics
                    and self.metric_comparability.evidence_status is EvidenceStatus.unknown
                ):
                    raise ContractValueError(
                        "constrained direct metrics require supported metric comparability"
                    )
            case ReplicationStrategy.conceptual_reimplementation:
                if not has_concrete_deviations:
                    raise ContractValueError(
                        "conceptual reimplementation requires concrete named deviations"
                    )
                if self.comparison_scope is not ComparisonScope.mechanism_only:
                    raise ContractValueError("conceptual reimplementation must be mechanism-only")
                if self.metric_comparability.evidence_status is not EvidenceStatus.unknown:
                    raise ContractValueError(
                        "conceptual reimplementation cannot claim paper metric comparability"
                    )
            case unreachable:
                assert_never(unreachable)
        return self

    def _validate_information_inventory(self) -> None:
        is_justified_complete = (
            self.information_completeness.assessment is CompletenessAssessment.complete
            and self.information_completeness.evidence_status
            in {EvidenceStatus.reported, EvidenceStatus.proposed}
        )
        if not self.missing_information and not is_justified_complete:
            raise ContractValueError(
                "empty missing information requires a supported complete assessment"
            )
        if self.missing_information and is_justified_complete:
            raise ContractValueError(
                "complete assessment conflicts with listed missing information"
            )


class InvestigationDirection(ContractModel):
    title: CompletionStr
    objective: CompletionStr
    replication_steps: tuple[ReplicationStep, ...] = Field(min_length=1)
    data: DataRequirements
    model: ModelRequirements
    compute: ComputeRequirements
    assumptions: tuple[EvidenceStatement, ...] = Field(min_length=1)


class InvestigationPlan(ContractModel):
    question: NonEmptyStr
    sources: tuple[SourceReference, ...] = Field(min_length=1)
    baseline_replication: BaselineReplication
    directions: tuple[InvestigationDirection, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_references(self) -> Self:
        known_refs = {source.paper_id for source in self.sources}
        unknown_refs = _collect_source_refs(self) - known_refs
        if unknown_refs:
            raise ContractValueError(
                f"unknown source references: {', '.join(sorted(unknown_refs))}"
            )
        return self


def _collect_source_refs(plan: InvestigationPlan) -> set[str]:
    refs = {plan.baseline_replication.core_paper_ref}
    baseline_statements = (
        plan.baseline_replication.protocol_equivalence,
        plan.baseline_replication.metric_comparability,
        *plan.baseline_replication.deviations,
    )
    for statement in baseline_statements:
        refs.update(statement.source_refs)
    refs.update(plan.baseline_replication.information_completeness.source_refs)
    for direction in plan.directions:
        statements = (
            direction.data.access,
            direction.data.license,
            direction.data.splits,
            direction.data.time_horizon,
            direction.data.granularity,
            direction.model.architecture,
            direction.model.code_availability,
            direction.model.checkpoint_availability,
            direction.compute.hardware,
            *direction.assumptions,
        )
        for statement in statements:
            refs.update(statement.source_refs)
        refs.update(direction.compute.vram_gb.source_refs)
        refs.update(direction.compute.gpu_hours.source_refs)
    return refs
