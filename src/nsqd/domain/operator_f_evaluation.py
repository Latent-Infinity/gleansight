from __future__ import annotations

import pydantic

from nsqd.domain.operator_f_evaluation_metrics import MetricTrustContext, evaluate_metrics
from nsqd.domain.operator_f_evaluation_readiness import (
    OperatorFHistoricalReadinessInputs,
    OperatorFHistoricalSourceGroup,
    historical_replay_components,
)
from nsqd.domain.operator_f_evaluation_support import (
    OperatorFEvaluationError,
    build_folds,
    build_shuffle,
    build_tracks,
    partition_source_groups,
    require_identical_tracks,
    result_digest,
)
from nsqd.domain.operator_f_evaluation_trust import (
    InterpretabilityRating,
    TrustedAdjudication,
    TrustedCorpusApproval,
    TrustedInterpretabilityReview,
    TrustedQualityReview,
    TrustedSourceGroupApproval,
)
from nsqd.domain.operator_f_evaluation_trust_rules import (
    partition_trusted_approval_eligibility,
    trusted_quality_weights,
)
from nsqd.domain.operator_f_evaluation_types import (
    ConfoundStratum,
    FoldDefinition,
    JsonValue,
    MetricName,
    MetricResult,
    MetricSeries,
    OperatorFEvaluationInputs,
    OperatorFEvaluationResult,
    OperatorFReportResult,
    OperatorFSourceGroup,
    OperatorFUnavailableResult,
    PrimaryMetric,
    RegisteredCoordinates,
    SourceProvenance,
    TrackReplay,
    UnavailableMetric,
    ValidationTarget,
)
from nsqd.domain.snapshot import canonical_json

__all__ = (
    "ConfoundStratum",
    "InterpretabilityRating",
    "JsonValue",
    "MetricName",
    "MetricResult",
    "MetricSeries",
    "OperatorFEvaluationError",
    "OperatorFEvaluationInputs",
    "OperatorFEvaluationResult",
    "OperatorFHistoricalReadinessInputs",
    "OperatorFHistoricalSourceGroup",
    "OperatorFReportResult",
    "OperatorFSourceGroup",
    "OperatorFUnavailableResult",
    "PrimaryMetric",
    "RegisteredCoordinates",
    "SourceProvenance",
    "TrustedAdjudication",
    "TrustedCorpusApproval",
    "TrustedInterpretabilityReview",
    "TrustedQualityReview",
    "TrustedSourceGroupApproval",
    "ValidationTarget",
    "evaluate_operator_f",
    "evaluate_operator_f_historical_readiness",
    "validate_operator_f_evaluation_result",
)

METRIC_NAMES: tuple[MetricName, ...] = (
    "held_out_gain",
    "density",
    "quality_weighted_diversity",
    "stability",
    "redundancy",
    "residual_variation",
    "confound_sensitivity",
    "interpretability",
)


def _base_payload(
    identities: tuple[tuple[str, ...], tuple[str, ...]],
    folds: FoldDefinition,
    tracks: tuple[TrackReplay, TrackReplay, TrackReplay],
) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "record_type": "operator_f_evaluation_result",
        "authorization_state": "report_only",
        "validation_target_scope": "evaluation_only",
        "runtime_authorized": False,
        "schema_admission_authorized": False,
        "evidence_sufficient": False,
        "recommendation": None,
        "threshold_status": "human_decision_required_before_outcome_unblinding",
        "thresholds": (),
        "eligible_source_group_identities": identities[0],
        "excluded_source_group_identities": identities[1],
        "fold_definition": folds.model_dump(mode="json"),
        "tracks": tuple(track.model_dump(mode="json") for track in tracks),
        "result_digest": "0" * 64,
    }


def _finalize_unavailable(
    payload: dict[str, JsonValue],
) -> OperatorFUnavailableResult:
    provisional = OperatorFUnavailableResult.model_validate_json(canonical_json(payload))
    digest = result_digest(provisional.model_dump(mode="json"))
    return provisional.model_copy(update={"result_digest": digest})


def _finalize_report(payload: dict[str, JsonValue]) -> OperatorFReportResult:
    provisional = OperatorFReportResult.model_validate_json(canonical_json(payload))
    digest = result_digest(provisional.model_dump(mode="json"))
    return provisional.model_copy(update={"result_digest": digest})


def _declared_fields_only(model: pydantic.BaseModel) -> bool:
    return model.__dict__.keys() == type(model).model_fields.keys()


def _input_models(inputs: OperatorFEvaluationInputs) -> tuple[pydantic.BaseModel, ...]:
    models: list[pydantic.BaseModel] = [inputs]
    for record in inputs.source_groups:
        models.extend((record, record.primary_metric, record.provenance))
        models.extend(record.provenance.confound_strata)
        if record.registered_coordinates is not None:
            models.append(record.registered_coordinates)
    for approval in inputs.trusted_approvals:
        models.extend((approval, *approval.adjudications, approval.corpus_approval))
    models.extend(inputs.trusted_quality_reviews)
    for review in inputs.interpretability_reviews:
        models.extend((review, *review.ratings))
    return tuple(models)


def _canonicalize_inputs(inputs: OperatorFEvaluationInputs) -> OperatorFEvaluationInputs:
    try:
        canonical = OperatorFEvaluationInputs.model_validate_json(
            canonical_json(inputs.model_dump(mode="json"))
        )
    except pydantic.ValidationError as exc:
        raise OperatorFEvaluationError(f"operator F trusted inputs are invalid: {exc}") from exc
    if not all(_declared_fields_only(model) for model in _input_models(inputs)):
        raise OperatorFEvaluationError("operator F trusted inputs are noncanonical")
    if canonical != inputs:
        raise OperatorFEvaluationError("operator F trusted inputs are noncanonical")
    return canonical


def evaluate_operator_f(inputs: OperatorFEvaluationInputs) -> OperatorFEvaluationResult:
    inputs = _canonicalize_inputs(inputs)
    structurally_eligible, structurally_excluded = partition_source_groups(inputs.source_groups)
    eligible, approval_excluded = partition_trusted_approval_eligibility(
        structurally_eligible, inputs.trusted_approvals
    )
    excluded = tuple(
        sorted(
            (*structurally_excluded, *approval_excluded),
            key=lambda record: record.canonical_work_identity,
        )
    )
    eligible_identities = tuple(record.canonical_work_identity for record in eligible)
    excluded_identities = tuple(record.canonical_work_identity for record in excluded)
    folds = build_folds(eligible if len(eligible) >= 5 else ())
    labels: tuple[tuple[str, ValidationTarget], ...] = tuple(
        (record.canonical_work_identity, record.validation_target)
        for record in eligible
        if record.validation_target is not None
    )
    shuffle = build_shuffle(eligible_identities)
    tracks = build_tracks(labels, folds, shuffle)
    base = _base_payload((eligible_identities, excluded_identities), folds, tracks)
    base["shuffle"] = shuffle.model_dump(mode="json")
    if len(eligible) < 5:
        base["evaluation_status"] = "unavailable"
        base["blocker"] = "insufficient_eligible_source_groups"
        base["metrics"] = tuple(
            UnavailableMetric(
                name=name,
                state="unavailable",
                reason="insufficient_eligible_source_groups",
            ).model_dump(mode="json")
            for name in METRIC_NAMES
        )
        return _finalize_unavailable(base)
    quality_weights = trusted_quality_weights(eligible, inputs.trusted_quality_reviews)
    require_identical_tracks(tracks)
    base["evaluation_status"] = "report_only"
    base["metrics"] = tuple(
        metric.model_dump(mode="json")
        for metric in evaluate_metrics(
            eligible,
            tracks,
            MetricTrustContext(
                quality_weights=tuple(sorted(quality_weights.items())),
                interpretability_reviews=inputs.interpretability_reviews,
                fold_definition=folds,
            ),
        )
    )
    return _finalize_report(base)


def evaluate_operator_f_historical_readiness(
    inputs: OperatorFHistoricalReadinessInputs,
) -> OperatorFUnavailableResult:
    try:
        canonical = OperatorFHistoricalReadinessInputs.model_validate_json(
            canonical_json(inputs.model_dump(mode="json"))
        )
    except pydantic.ValidationError as exc:
        raise OperatorFEvaluationError(
            "historical Operator F readiness inputs are invalid"
        ) from exc
    if not _declared_fields_only(inputs) or not all(
        _declared_fields_only(group) for group in inputs.source_groups
    ):
        raise OperatorFEvaluationError("historical Operator F readiness inputs are noncanonical")
    if canonical != inputs:
        raise OperatorFEvaluationError("historical Operator F readiness inputs are noncanonical")
    identities, folds, shuffle, tracks = historical_replay_components(canonical)
    base = _base_payload(identities, folds, tracks)
    base["shuffle"] = shuffle.model_dump(mode="json")
    base["evaluation_status"] = "unavailable"
    base["blocker"] = "insufficient_eligible_source_groups"
    base["metrics"] = tuple(
        UnavailableMetric(
            name=name,
            state="unavailable",
            reason="insufficient_eligible_source_groups",
        ).model_dump(mode="json")
        for name in METRIC_NAMES
    )
    return _finalize_unavailable(base)


def validate_operator_f_evaluation_result(
    payload: dict[str, JsonValue],
    *,
    trusted_inputs: OperatorFEvaluationInputs,
) -> OperatorFEvaluationResult:
    trusted_inputs = _canonicalize_inputs(trusted_inputs)
    try:
        status = payload.get("evaluation_status")
        if status == "unavailable":
            result: OperatorFEvaluationResult = OperatorFUnavailableResult.model_validate_json(
                canonical_json(payload)
            )
        elif status == "report_only":
            result = OperatorFReportResult.model_validate_json(canonical_json(payload))
        else:
            raise OperatorFEvaluationError("operator F evaluation result shape is invalid")
    except pydantic.ValidationError as exc:
        raise OperatorFEvaluationError("operator F evaluation result shape is invalid") from exc
    if result.result_digest != result_digest(result.model_dump(mode="json")):
        raise OperatorFEvaluationError("operator F evaluation result digest does not match")
    require_identical_tracks(result.tracks)
    expected = evaluate_operator_f(trusted_inputs)
    if result != expected:
        raise OperatorFEvaluationError("operator F evaluation result does not match trusted inputs")
    return result
