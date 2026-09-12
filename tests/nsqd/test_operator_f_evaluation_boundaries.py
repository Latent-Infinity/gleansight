from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_remediation_support import quality_review
from tests.nsqd.operator_f_evaluation_support import (
    approval,
    balanced_inputs,
    inputs,
    result_digest,
    source_group,
)


def test_missing_provenance_is_rejected_at_the_typed_boundary() -> None:
    payload = source_group(0).model_dump(mode="python")
    payload.pop("provenance")

    with pytest.raises(ValidationError):
        operator_f.OperatorFSourceGroup.model_validate(payload)


@pytest.mark.parametrize("duplicate", ["group", "version"])
def test_duplicate_group_or_version_identity_is_rejected_before_eligibility(
    duplicate: str,
) -> None:
    records = [source_group(index) for index in range(5)]
    if duplicate == "group":
        records[4] = records[4].model_copy(
            update={"canonical_work_identity": records[0].canonical_work_identity}
        )
    else:
        records[4] = records[4].model_copy(
            update={"all_version_identities": records[0].all_version_identities}
        )

    with pytest.raises(ValidationError, match="duplicate"):
        inputs(records)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_supplied_measurements_are_rejected(value: float) -> None:
    payload = quality_review(source_group(0)).model_dump(mode="python")
    payload["weight"] = value

    with pytest.raises(ValidationError):
        operator_f.TrustedQualityReview.model_validate(payload)


def test_imputation_and_candidate_authority_claims_are_rejected() -> None:
    payload = inputs(source_group(index) for index in range(5)).model_dump(mode="python")

    for field, value in (
        ("imputation_authorized", True),
        ("runtime_authorized", True),
        ("schema_admission_authorized", True),
        ("evidence_sufficient", True),
        ("approval", "self-asserted"),
    ):
        altered = dict(payload)
        altered[field] = value
        with pytest.raises(ValidationError):
            operator_f.OperatorFEvaluationInputs.model_validate(altered)


def test_record_cannot_self_assert_approval_or_authority() -> None:
    payload = source_group(0).model_dump(mode="python")

    for field in ("approved", "authority", "runtime_authorized"):
        altered = dict(payload)
        altered[field] = True
        with pytest.raises(ValidationError):
            operator_f.OperatorFSourceGroup.model_validate(altered)


def test_digest_mismatch_reviewer_disagreement_and_missing_approval_are_ineligible() -> None:
    records = tuple(source_group(index) for index in range(5))
    approvals = tuple(approval(record) for record in records)
    mismatch = approvals[0].model_copy(update={"observed_source_byte_sha256": "f" * 64})
    disagreement = approval(records[0], disagreement=True)

    results = (
        operator_f.evaluate_operator_f(inputs(records, approvals=(mismatch, *approvals[1:]))),
        operator_f.evaluate_operator_f(inputs(records, approvals=(disagreement, *approvals[1:]))),
        operator_f.evaluate_operator_f(inputs(records, approvals=approvals[:-1])),
    )

    assert all(isinstance(result, operator_f.OperatorFUnavailableResult) for result in results)
    assert all(len(result.eligible_source_group_identities) == 4 for result in results)
    assert all(result.fold_definition.assignments == () for result in results)


def test_self_review_is_ineligible() -> None:
    records = tuple(source_group(index) for index in range(5))
    approvals = list(approval(record) for record in records)
    first = approvals[0]
    self_review = first.adjudications[0].model_copy(
        update={"reviewer_identity": records[0].provenance.producer_identity}
    )
    approvals[0] = first.model_copy(update={"adjudications": (self_review, first.adjudications[1])})

    result = operator_f.evaluate_operator_f(inputs(records, approvals=tuple(approvals)))

    assert isinstance(result, operator_f.OperatorFUnavailableResult)
    assert len(result.eligible_source_group_identities) == 4
    assert result.fold_definition.assignments == ()


def test_replay_validator_rejects_population_fold_and_metric_tampering() -> None:
    trusted_inputs = balanced_inputs()
    result = operator_f.evaluate_operator_f(trusted_inputs)
    assert isinstance(result, operator_f.OperatorFReportResult)
    payload = result.model_dump(mode="json")
    assert result.result_digest == result_digest(payload)
    assert (
        operator_f.validate_operator_f_evaluation_result(
            payload,
            trusted_inputs=trusted_inputs,
        )
        == result
    )

    altered_population = result.model_dump(mode="json")
    altered_population["tracks"][0]["eligible_source_group_identities"].pop()
    altered_population["result_digest"] = result_digest(altered_population)
    with pytest.raises(ValueError, match="population"):
        operator_f.validate_operator_f_evaluation_result(
            altered_population,
            trusted_inputs=trusted_inputs,
        )

    altered_fold = result.model_dump(mode="json")
    altered_fold["tracks"][1]["fold_assignments"][0]["fold_index"] = 4
    altered_fold["result_digest"] = result_digest(altered_fold)
    with pytest.raises(ValueError, match="fold"):
        operator_f.validate_operator_f_evaluation_result(
            altered_fold,
            trusted_inputs=trusted_inputs,
        )

    altered_metric = result.model_dump(mode="json")
    altered_metric["metrics"][0]["series"][0]["aggregate_value"] = 99.0
    altered_metric["result_digest"] = result_digest(altered_metric)
    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.validate_operator_f_evaluation_result(
            altered_metric,
            trusted_inputs=trusted_inputs,
        )


def test_result_boundary_rejects_nonfinite_and_authority_widening() -> None:
    trusted_inputs = balanced_inputs()
    result = operator_f.evaluate_operator_f(trusted_inputs)
    assert isinstance(result, operator_f.OperatorFReportResult)

    for field, value in (
        ("runtime_authorized", True),
        ("schema_admission_authorized", True),
        ("evidence_sufficient", True),
        ("decision", "admit"),
    ):
        payload = result.model_dump(mode="json")
        payload[field] = value
        with pytest.raises(ValueError, match="shape"):
            operator_f.validate_operator_f_evaluation_result(payload, trusted_inputs=trusted_inputs)

    payload = result.model_dump(mode="json")
    payload["metrics"][0]["series"][0]["aggregate_value"] = math.inf
    payload["result_digest"] = result_digest(payload)
    with pytest.raises(ValueError, match="shape"):
        operator_f.validate_operator_f_evaluation_result(payload, trusted_inputs=trusted_inputs)


def test_optional_metric_prerequisites_use_protocol_specific_unavailable_reasons() -> None:
    records = tuple(
        source_group(index, confound_value="b" if index == 0 else "a") for index in range(5)
    )
    quality_reviews = tuple(quality_review(record, 0.0) for record in records)

    result = operator_f.evaluate_operator_f(inputs(records, quality_reviews=quality_reviews))

    assert isinstance(result, operator_f.OperatorFReportResult)
    metrics = {metric.name: metric for metric in result.metrics}
    assert metrics["quality_weighted_diversity"].reason == "zero_total_held_out_quality_weight"
    assert (
        metrics["confound_sensitivity"].reason
        == "declared_stratum_missing_eligible_held_out_observation"
    )
    assert (
        metrics["interpretability"].reason == "missing_independent_blinded_interpretability_rating"
    )


def test_missing_optional_measurements_remain_explicitly_unavailable() -> None:
    records = tuple(source_group(index, confound_value=None) for index in range(5))

    result = operator_f.evaluate_operator_f(inputs(records))

    assert isinstance(result, operator_f.OperatorFReportResult)
    metrics = {metric.name: metric for metric in result.metrics}
    assert metrics["quality_weighted_diversity"].reason == "missing_blinded_quality_weight"
    assert metrics["confound_sensitivity"].reason == "no_predeclared_confound_strata"
