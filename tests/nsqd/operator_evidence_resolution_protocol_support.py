from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal

import pydantic

NonBlank = Annotated[pydantic.StrictStr, pydantic.Field(min_length=1, pattern=r"\S")]
Sha256 = Annotated[pydantic.StrictStr, pydantic.Field(pattern=r"^[0-9a-f]{64}$")]
EXPECTED_IDENTITY_FIELDS: Final = {
    "source_class",
    "stable_source_id",
    "version_id",
    "retrieval_uri",
    "content_sha256",
}
EXPECTED_C_CONTROLS: Final = {
    "normalized_shared_term_control_under_identical_query_budget",
    "sha256_seeded_shuffled_literature_pair_control_under_identical_query_budget",
}
EXPECTED_F_METRICS: Final = {
    "held_out_gain",
    "density",
    "quality_weighted_diversity",
    "stability",
    "redundancy",
    "residual_variation",
    "confound_sensitivity",
    "interpretability",
}
EXPECTED_RETENTION_STATES: Final = {
    "retained_repository_authorized",
    "retained_authorized_external_store",
    "not_retained_repository_policy",
}


class FrozenModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", strict=True)


class RuntimeStates(FrozenModel):
    operator_c: Literal["disabled"]
    operator_d: Literal["disabled"]
    operator_f: Literal["disabled"]
    operator_g: Literal["disabled"]
    operator_e: Literal["disabled_absent_explicit_override"]


class Authority(FrozenModel):
    authorization_state: Literal["report_only"]
    validation_target_scope: Literal["evaluation_only"]
    runtime_states: RuntimeStates
    schema_admission_authorized: Literal[False]
    runtime_change_authorized: Literal[False]
    operator_g_restart_authorized: Literal[False]


class DiscoveryEnvelope(FrozenModel):
    maximum_query_batches: Literal[3]
    maximum_candidates_per_batch: Literal[25]
    maximum_staged_imports_per_pass: Literal[3]
    widening_requires_explicit_human_authorization: Literal[True]


class SourceIdentity(FrozenModel):
    identity_fields: tuple[NonBlank, ...]
    deduplication_key_fields: tuple[NonBlank, ...]
    version_rules: tuple[NonBlank, ...]
    duplicate_identity_action: Literal["reject_before_eligibility"]


class TypedRelation(FrozenModel):
    required_sides: tuple[Literal["source", "target"], Literal["source", "target"]]
    required_fields_per_side: tuple[NonBlank, ...]
    relation_fields: tuple[NonBlank, ...]
    passage_binding_required: Literal[True]


class OperatorCProtocol(FrozenModel):
    search_questions: tuple[NonBlank, ...]
    bridge_eligibility_conditions: tuple[NonBlank, ...]
    typed_relation: TypedRelation
    direct_a_to_c_prior_art_required: Literal[True]
    counterevidence_required: Literal[True]
    negative_controls: tuple[NonBlank, ...]
    query_budget: DiscoveryEnvelope
    positive_verdict_conditions: tuple[NonBlank, ...]
    stop_conditions: tuple[NonBlank, ...]


class FoldProtocol(FrozenModel):
    unit: Literal["independent_source_group"]
    fold_count: Literal[5]
    algorithm: Literal["sha256_seeded_source_group_round_robin/v1"]
    seed: Literal["operator-f/evidence-resolution/source-grouped-five-fold/v1"]
    preimage: Literal["utf8(seed + ':' + canonical_source_group_identity)"]
    ordering: Literal["ascending_sha256_then_canonical_source_group_identity"]
    assignment: Literal["zero_based_rank_modulo_5"]


class MetricDefinition(FrozenModel):
    name: NonBlank
    definition: NonBlank
    unavailable_when: NonBlank


class BlindingProtocol(FrozenModel):
    quality_review_blinded_to: tuple[NonBlank, ...]
    interpretability_review_blinded_to: tuple[NonBlank, ...]
    thresholds_must_be_approved_before: Literal["any_decision_bearing_outcome_is_unblinded"]
    imputation_authorized: Literal[False]


class ThresholdPolicy(FrozenModel):
    status: Literal["human_decision_required_before_outcome_unblinding"]
    numeric_thresholds: tuple[()]
    approved_at_utc: None
    outcomes_observed_at_approval: Literal[False]
    post_outcome_thresholds_authorized: Literal[False]


class OperatorFProtocol(FrozenModel):
    source_group_identity_fields: tuple[NonBlank, ...]
    eligibility_conditions: tuple[NonBlank, ...]
    exclusion_conditions: tuple[NonBlank, ...]
    exclude_before_fold_assignment: Literal[True]
    versions_share_one_source_group: Literal[True]
    minimum_eligible_source_groups: Literal[5]
    folds: FoldProtocol
    tracks: tuple[
        Literal["current_registered_axes"],
        Literal["current_axes_plus_validation_target"],
        Literal["current_axes_plus_shuffled_validation_target"],
    ]
    shuffled_label_control: Literal["sha256_seeded_permutation_within_eligible_population/v1"]
    identical_population_and_folds_across_tracks: Literal[True]
    training_only_preprocessing: Literal[True]
    metrics: tuple[MetricDefinition, ...]
    blinding: BlindingProtocol
    threshold_policy: ThresholdPolicy
    positive_selection_conditions: tuple[NonBlank, ...]
    stop_conditions: tuple[NonBlank, ...]


class ExternalTrust(FrozenModel):
    record_fields_are_authority: Literal[False]
    separately_supplied_approval_required: Literal[True]
    approval_binding_fields: tuple[NonBlank, ...]
    evidence_bytes_must_match_declared_digests: Literal[True]


class ExperimentGate(FrozenModel):
    existing_experiment_preferred: Literal[True]
    new_experiment_requires_scientific_purpose: Literal[True]
    new_experiment_requires_explicit_authorization: Literal[True]
    authorization_request_fields: tuple[NonBlank, ...]
    experiment_must_not_be_designed_to_create_failure: Literal[True]


class ConditionalAblation(FrozenModel):
    activation_condition: Literal["at_least_one_real_independently_approved_record_exists"]
    memory_tracks: tuple[NonBlank, ...]
    restart_policy_tracks: tuple[NonBlank, ...]
    common_experiments_required: Literal[True]


class OperatorGProtocol(FrozenModel):
    required_registered_experiment_fields: tuple[NonBlank, ...]
    forbidden_candidate_classes: tuple[NonBlank, ...]
    experiment_purpose: ExperimentGate
    external_trust: ExternalTrust
    changed_condition_requirements: tuple[NonBlank, ...]
    restart_condition_requirements: tuple[NonBlank, ...]
    conditional_ablations: ConditionalAblation
    decision_separation: tuple[NonBlank, ...]
    stop_conditions: tuple[NonBlank, ...]


class ReviewerIndependence(FrozenModel):
    producer_identity_required: Literal[True]
    producer_session_required: Literal[True]
    reviewer_identity_required: Literal[True]
    reviewer_session_required: Literal[True]
    reviewer_must_differ_from_producer: Literal[True]
    reviewer_session_must_differ_from_producer_session: Literal[True]
    self_review_authorized: Literal[False]
    technical_review_is_human_acceptance: Literal[False]


class AccessRetention(FrozenModel):
    source_byte_states: tuple[NonBlank, ...]
    bibliographic_response_states: tuple[NonBlank, ...]
    required_retention_record_fields: tuple[NonBlank, ...]
    negative_null_unavailable_and_counterevidence_retained: Literal[True]
    paid_or_private_access_requires_authorization: Literal[True]
    nonlocal_compute_requires_authorization: Literal[True]
    retention_outside_repository_policy_requires_authorization: Literal[True]
    predecessor_retention_claims_inherited: Literal[False]


class ProtocolPacket(FrozenModel):
    schema_version: Literal[1]
    packet_kind: Literal["operator_evidence_resolution_protocol"]
    frozen_at_utc: NonBlank
    cutoff_utc: NonBlank
    acquisition_outcomes_observed: Literal[False]
    authority: Authority
    discovery_envelope: DiscoveryEnvelope
    source_identity: SourceIdentity
    operator_c: OperatorCProtocol
    operator_f: OperatorFProtocol
    operator_g: OperatorGProtocol
    reviewer_independence: ReviewerIndependence
    access_and_retention: AccessRetention
    global_stop_conditions: tuple[NonBlank, ...]


class PacketManifest(FrozenModel):
    schema_version: Literal[1]
    artifact_sha256: dict[NonBlank, Sha256]
    packet_digest: Sha256


@dataclass(frozen=True, slots=True)
class ProtocolValidationError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProtocolValidationError(reason)


def _utc(value: str) -> datetime:
    _require(value.endswith("Z"), "protocol timestamps must use the UTC Z suffix")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo == UTC, "protocol timestamps must be UTC")
    return parsed


def validate_packet(packet_root: Path) -> ProtocolPacket:
    protocol_path = packet_root / "protocol.json"
    protocol = ProtocolPacket.model_validate_json(protocol_path.read_text(encoding="utf-8"))
    manifest = PacketManifest.model_validate_json(
        (packet_root / "packet-manifest.json").read_text(encoding="utf-8")
    )
    _utc(protocol.frozen_at_utc)
    _utc(protocol.cutoff_utc)
    _require(protocol.frozen_at_utc == protocol.cutoff_utc, "cutoff must equal freeze instant")
    identities = protocol.source_identity.identity_fields
    deduplication = protocol.source_identity.deduplication_key_fields
    _require(len(identities) == len(set(identities)), "source identity fields must be unique")
    _require(len(deduplication) == len(set(deduplication)), "deduplication fields must be unique")
    _require(set(identities) == EXPECTED_IDENTITY_FIELDS, "source identity fields are incomplete")
    _require(
        protocol.operator_c.typed_relation.required_sides == ("source", "target"),
        "C relation must be two-sided",
    )
    _require(len(protocol.operator_c.search_questions) >= 3, "C search questions are incomplete")
    _require(
        set(protocol.operator_c.negative_controls) == EXPECTED_C_CONTROLS,
        "C negative controls are incomplete",
    )
    metric_names = tuple(metric.name for metric in protocol.operator_f.metrics)
    _require(
        set(metric_names) == EXPECTED_F_METRICS and len(metric_names) == 8,
        "F metric set is incomplete",
    )
    _require(
        len(protocol.operator_g.required_registered_experiment_fields) >= 12,
        "G intake fields are incomplete",
    )
    source_states = set(protocol.access_and_retention.source_byte_states)
    response_states = set(protocol.access_and_retention.bibliographic_response_states)
    _require(
        source_states == EXPECTED_RETENTION_STATES | {"unavailable_from_source"},
        "source-byte retention states are incomplete",
    )
    _require(
        response_states == EXPECTED_RETENTION_STATES | {"unavailable_from_service"},
        "bibliographic-response retention states are incomplete",
    )
    _require(set(manifest.artifact_sha256) == {"protocol.json"}, "manifest members are not closed")
    artifact_digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    _require(manifest.artifact_sha256["protocol.json"] == artifact_digest, "member digest mismatch")
    preimage = json.dumps(manifest.artifact_sha256, sort_keys=True, separators=(",", ":")).encode()
    _require(
        manifest.packet_digest == hashlib.sha256(preimage).hexdigest(),
        "packet digest mismatch",
    )
    return protocol
