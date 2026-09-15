from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Self, assert_never

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StringConstraints,
    model_validator,
)

_RESERVED_PLACEHOLDERS = frozenset({"tbd", "todo", "n/a", "unknown", "none"})


@dataclass(frozen=True, slots=True)
class ContractValueError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def _reject_reserved_placeholder(value: str) -> str:
    if " ".join(value.split()).casefold() in _RESERVED_PLACEHOLDERS:
        raise ContractValueError("reserved placeholders must use structured unknown fields")
    return value


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CompletionStr = Annotated[NonEmptyStr, AfterValidator(_reject_reserved_placeholder)]
NonNegativeFiniteFloat = Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]


class EvidenceStatus(StrEnum):
    reported = "reported"
    proposed = "proposed"
    unknown = "unknown"


class ClaimKind(StrEnum):
    fact = "fact"
    inference = "inference"
    proposal = "proposal"


class StepStatus(StrEnum):
    not_started = "not_started"
    blocked = "blocked"
    verified = "verified"


class ComputeFeasibilityTier(StrEnum):
    local_cpu = "local_cpu"
    single_gpu = "single_gpu"
    multi_gpu = "multi_gpu"
    cluster = "cluster"
    unknown = "unknown"


class CompletenessAssessment(StrEnum):
    complete = "complete"
    incomplete = "incomplete"


class ContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceReference(ContractModel):
    paper_id: NonEmptyStr
    title: CompletionStr | None


class EvidenceStatement(ContractModel):
    claim_kind: ClaimKind
    evidence_status: EvidenceStatus
    value: CompletionStr | None
    source_refs: tuple[NonEmptyStr, ...]
    uncertainty_rationale: CompletionStr | None

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        match self.evidence_status:
            case EvidenceStatus.reported:
                if self.value is None or not self.source_refs:
                    raise ContractValueError("reported evidence requires value and sources")
            case EvidenceStatus.proposed:
                if self.value is None:
                    raise ContractValueError("proposed evidence requires a value")
                if not self.source_refs and self.uncertainty_rationale is None:
                    raise ContractValueError("proposed evidence requires support or uncertainty")
            case EvidenceStatus.unknown:
                if self.value is not None:
                    raise ContractValueError("unknown evidence cannot contain a value")
                if self.uncertainty_rationale is None:
                    raise ContractValueError("unknown evidence requires an uncertainty rationale")
            case unreachable:
                assert_never(unreachable)
        return self


class InformationCompleteness(ContractModel):
    evidence_status: EvidenceStatus
    assessment: CompletenessAssessment | None
    source_refs: tuple[NonEmptyStr, ...]
    uncertainty_rationale: CompletionStr | None

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        match self.evidence_status:
            case EvidenceStatus.reported:
                if self.assessment is None or not self.source_refs:
                    raise ContractValueError(
                        "reported completeness requires assessment and sources"
                    )
            case EvidenceStatus.proposed:
                if self.assessment is None or self.uncertainty_rationale is None:
                    raise ContractValueError(
                        "proposed completeness requires assessment and rationale"
                    )
            case EvidenceStatus.unknown:
                if self.assessment is not None or self.uncertainty_rationale is None:
                    raise ContractValueError(
                        "unknown completeness requires null assessment and rationale"
                    )
            case unreachable:
                assert_never(unreachable)
        return self


class NumericEstimate(ContractModel):
    claim_kind: ClaimKind
    evidence_status: EvidenceStatus
    value: NonNegativeFiniteFloat | None
    unit: CompletionStr
    basis: CompletionStr | None
    source_refs: tuple[NonEmptyStr, ...]
    uncertainty_rationale: CompletionStr | None

    @model_validator(mode="after")
    def validate_certainty(self) -> Self:
        match self.evidence_status:
            case EvidenceStatus.reported:
                if self.value is None or self.basis is None or not self.source_refs:
                    raise ContractValueError(
                        "reported estimates require value, basis, and citation"
                    )
            case EvidenceStatus.proposed:
                if self.value is None or self.basis is None:
                    raise ContractValueError(
                        "proposed estimates require value and assumption basis"
                    )
                if not self.source_refs and self.uncertainty_rationale is None:
                    raise ContractValueError("proposed estimates require support or uncertainty")
            case EvidenceStatus.unknown:
                if self.value is not None or self.basis is not None:
                    raise ContractValueError("unknown estimates require null value and basis")
                if self.uncertainty_rationale is None:
                    raise ContractValueError("unknown estimates require an uncertainty rationale")
            case unreachable:
                assert_never(unreachable)
        return self


class ReplicationStep(ContractModel):
    description: CompletionStr
    status: StepStatus
    evidence_refs: tuple[NonEmptyStr, ...]
    blocked_reason: CompletionStr | None

    @model_validator(mode="after")
    def validate_status_evidence(self) -> Self:
        match self.status:
            case StepStatus.not_started:
                if self.blocked_reason is not None:
                    raise ContractValueError("blocked reason is only valid for blocked steps")
            case StepStatus.blocked:
                if self.blocked_reason is None:
                    raise ContractValueError("blocked steps require a reason")
            case StepStatus.verified:
                if self.blocked_reason is not None:
                    raise ContractValueError("blocked reason is only valid for blocked steps")
                if not self.evidence_refs:
                    raise ContractValueError("verified steps require execution evidence references")
            case unreachable:
                assert_never(unreachable)
        return self


class DataRequirements(ContractModel):
    access: EvidenceStatement
    license: EvidenceStatement
    splits: EvidenceStatement
    time_horizon: EvidenceStatement
    granularity: EvidenceStatement


class ModelRequirements(ContractModel):
    architecture: EvidenceStatement
    code_availability: EvidenceStatement
    checkpoint_availability: EvidenceStatement


class ComputeRequirements(ContractModel):
    feasibility_tier: ComputeFeasibilityTier
    hardware: EvidenceStatement
    vram_gb: NumericEstimate
    gpu_hours: NumericEstimate
