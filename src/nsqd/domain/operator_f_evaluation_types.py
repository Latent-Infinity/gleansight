from __future__ import annotations

from typing import Annotated, Literal, Self

import pydantic

from .operator_f_evaluation_trust import (
    TrustedInterpretabilityReview,
    TrustedQualityReview,
    TrustedSourceGroupApproval,
)
from .operator_f_evaluation_validation import (
    FiniteFloat,
    NonBlank,
    OperatorFValidationError,
    Sha256,
)

type JsonValue = (
    str | int | float | bool | None | list[JsonValue] | tuple[JsonValue, ...] | dict[str, JsonValue]
)

type ValidationTarget = Literal[
    "representation_fidelity",
    "predictive_task",
    "economic_utility",
    "calibrated_risk",
]
type TrackId = Literal[
    "current_registered_axes",
    "current_axes_plus_validation_target",
    "current_axes_plus_shuffled_validation_target",
]
type MetricName = Literal[
    "held_out_gain",
    "density",
    "quality_weighted_diversity",
    "stability",
    "redundancy",
    "residual_variation",
    "confound_sensitivity",
    "interpretability",
]
type MetricUnavailableReason = Literal[
    "insufficient_eligible_source_groups",
    "occupied_held_out_cell_count_zero",
    "missing_blinded_quality_weight",
    "duplicate_occupied_cell_quality_weight_undefined",
    "zero_total_held_out_quality_weight",
    "unavailable_or_nonfinite_foldwise_gain",
    "degenerate_contingency_table",
    "held_out_category_absent_from_training_groups",
    "zero_held_out_validation_target_entropy",
    "required_category_support_absent_from_training_groups",
    "no_predeclared_confound_strata",
    "declared_stratum_missing_eligible_held_out_observation",
    "missing_independent_blinded_interpretability_rating",
]


class FrozenModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", strict=True)


class RegisteredCoordinates(FrozenModel):
    mechanism: NonBlank
    target: NonBlank
    horizon: NonBlank


class PrimaryMetric(FrozenModel):
    name: NonBlank


class ConfoundStratum(FrozenModel):
    name: NonBlank
    value: NonBlank


class SourceProvenance(FrozenModel):
    source_path: NonBlank
    producer_identity: NonBlank
    producer_session: NonBlank
    confound_strata: tuple[ConfoundStratum, ...] = ()

    @pydantic.model_validator(mode="after")
    def require_unique_confound_names(self) -> Self:
        names = tuple(item.name for item in self.confound_strata)
        if len(names) != len(set(names)):
            raise OperatorFValidationError("confound stratum names must be unique")
        return self


class OperatorFSourceGroup(FrozenModel):
    canonical_work_identity: NonBlank
    all_version_identities: tuple[NonBlank, ...]
    approved_source_byte_sha256: Sha256
    registered_coordinates: RegisteredCoordinates | None
    validation_target: ValidationTarget | None
    primary_metric: PrimaryMetric
    provenance: SourceProvenance

    @pydantic.model_validator(mode="after")
    def require_unique_versions(self) -> Self:
        if not self.all_version_identities:
            raise OperatorFValidationError("at least one version identity is required")
        if len(self.all_version_identities) != len(set(self.all_version_identities)):
            raise OperatorFValidationError("duplicate version identity within source group")
        return self


class OperatorFEvaluationInputs(FrozenModel):
    source_groups: tuple[OperatorFSourceGroup, ...]
    trusted_approvals: tuple[TrustedSourceGroupApproval, ...]
    trusted_quality_reviews: tuple[TrustedQualityReview, ...] = ()
    interpretability_reviews: tuple[TrustedInterpretabilityReview, ...] = ()
    imputation_authorized: Literal[False]

    @pydantic.model_validator(mode="after")
    def reject_duplicate_identity_or_version(self) -> Self:
        identities = tuple(item.canonical_work_identity for item in self.source_groups)
        versions = tuple(
            version for item in self.source_groups for version in item.all_version_identities
        )
        approval_identities = tuple(item.canonical_work_identity for item in self.trusted_approvals)
        quality_identities = tuple(
            item.canonical_work_identity for item in self.trusted_quality_reviews
        )
        if len(identities) != len(set(identities)):
            raise OperatorFValidationError("duplicate canonical work identity")
        if len(versions) != len(set(versions)):
            raise OperatorFValidationError("duplicate version identity across source groups")
        if len(approval_identities) != len(set(approval_identities)):
            raise OperatorFValidationError("duplicate trusted approval identity")
        if len(quality_identities) != len(set(quality_identities)):
            raise OperatorFValidationError("duplicate trusted quality review identity")
        return self


class FoldAssignment(FrozenModel):
    canonical_work_identity: NonBlank
    digest: Sha256
    fold_index: Annotated[pydantic.StrictInt, pydantic.Field(ge=0, le=4)]


class FoldDefinition(FrozenModel):
    algorithm: Literal["sha256_seeded_source_group_round_robin/v1"]
    seed: Literal["operator-f/evidence-resolution/source-grouped-five-fold/v1"]
    preimage: Literal["utf8(seed + ':' + canonical_source_group_identity)"]
    ordering: Literal["ascending_sha256_then_canonical_source_group_identity"]
    assignment: Literal["zero_based_rank_modulo_5"]
    assignments: tuple[FoldAssignment, ...]


class ShuffleAssignment(FrozenModel):
    canonical_work_identity: NonBlank
    receives_validation_target_from: NonBlank


class ShuffleDefinition(FrozenModel):
    algorithm: Literal["sha256_seeded_permutation_within_eligible_population/v1"]
    seed: Literal[
        "operator-f/evidence-resolution/source-grouped-five-fold/v1:shuffled-validation-target"
    ]
    fixed_point_free: pydantic.StrictBool
    assignments: tuple[ShuffleAssignment, ...]


class TrackLabel(FrozenModel):
    canonical_work_identity: NonBlank
    validation_target: ValidationTarget


class TrackReplay(FrozenModel):
    track_id: TrackId
    eligible_source_group_identities: tuple[NonBlank, ...]
    fold_assignments: tuple[FoldAssignment, ...]
    labels: tuple[TrackLabel, ...]


class MetricObservation(FrozenModel):
    label: NonBlank
    fold_index: Annotated[pydantic.StrictInt, pydantic.Field(ge=0, le=4)] | None
    state: Literal["available", "unavailable"]
    value: FiniteFloat | None
    reason: MetricUnavailableReason | None


class MetricSeries(FrozenModel):
    track_id: TrackId
    state: Literal["available", "unavailable"]
    observations: tuple[MetricObservation, ...]
    arithmetic_mean: FiniteFloat | None
    aggregate_value: FiniteFloat | None
    reason: MetricUnavailableReason | None


class MetricResult(FrozenModel):
    name: MetricName
    state: Literal["available", "unavailable"]
    series: tuple[MetricSeries, ...]
    reason: MetricUnavailableReason | None
    disagreements: tuple[NonBlank, ...] = ()


class UnavailableMetric(FrozenModel):
    name: MetricName
    state: Literal["unavailable"]
    reason: Literal["insufficient_eligible_source_groups"]


class OperatorFUnavailableResult(FrozenModel):
    schema_version: Literal[1]
    record_type: Literal["operator_f_evaluation_result"]
    evaluation_status: Literal["unavailable"]
    blocker: Literal["insufficient_eligible_source_groups"]
    authorization_state: Literal["report_only"]
    validation_target_scope: Literal["evaluation_only"]
    runtime_authorized: Literal[False]
    schema_admission_authorized: Literal[False]
    evidence_sufficient: Literal[False]
    recommendation: None
    threshold_status: Literal["human_decision_required_before_outcome_unblinding"]
    thresholds: tuple[()]
    eligible_source_group_identities: tuple[NonBlank, ...]
    excluded_source_group_identities: tuple[NonBlank, ...]
    fold_definition: FoldDefinition
    shuffle: ShuffleDefinition
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay]
    metrics: tuple[UnavailableMetric, ...]
    result_digest: Sha256


class OperatorFReportResult(FrozenModel):
    schema_version: Literal[1]
    record_type: Literal["operator_f_evaluation_result"]
    evaluation_status: Literal["report_only"]
    authorization_state: Literal["report_only"]
    validation_target_scope: Literal["evaluation_only"]
    runtime_authorized: Literal[False]
    schema_admission_authorized: Literal[False]
    evidence_sufficient: Literal[False]
    recommendation: None
    threshold_status: Literal["human_decision_required_before_outcome_unblinding"]
    thresholds: tuple[()]
    eligible_source_group_identities: tuple[NonBlank, ...]
    excluded_source_group_identities: tuple[NonBlank, ...]
    fold_definition: FoldDefinition
    shuffle: ShuffleDefinition
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay]
    metrics: tuple[MetricResult, ...]
    result_digest: Sha256


type OperatorFEvaluationResult = OperatorFUnavailableResult | OperatorFReportResult
