from __future__ import annotations

import pytest

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_remediation_support import (
    interpretability_reviews,
    quality_review,
    records_in_fold_order,
)
from tests.nsqd.operator_f_evaluation_support import inputs, source_group


def _metric(
    result: operator_f.OperatorFReportResult,
    name: operator_f.MetricName,
) -> operator_f.MetricResult:
    return next(metric for metric in result.metrics if metric.name == name)


def test_fold_metadata_uses_frozen_source_group_identity_text() -> None:
    result = operator_f.evaluate_operator_f(inputs(source_group(index) for index in range(5)))

    assert result.fold_definition.preimage == ("utf8(seed + ':' + canonical_source_group_identity)")
    assert result.fold_definition.ordering == (
        "ascending_sha256_then_canonical_source_group_identity"
    )


@pytest.mark.parametrize("field", ["imputation_authorized", "runtime_authorized"])
def test_public_entry_rejects_noncanonical_typed_input(field: str) -> None:
    trusted = inputs(source_group(index) for index in range(5))
    altered = trusted.model_copy(update={field: True})

    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.evaluate_operator_f(altered)


def test_public_entry_rejects_nested_model_copy_mutation() -> None:
    trusted = inputs(source_group(index) for index in range(5))
    altered_source = trusted.source_groups[0].model_copy(
        update={
            "provenance": trusted.source_groups[0].provenance.model_copy(
                update={"producer_identity": ""}
            )
        }
    )
    altered = trusted.model_copy(
        update={"source_groups": (altered_source, *trusted.source_groups[1:])}
    )

    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.evaluate_operator_f(altered)


def test_public_entry_rejects_nested_authority_injection() -> None:
    trusted = inputs(source_group(index) for index in range(5))
    altered_source = trusted.source_groups[0].model_copy(update={"runtime_authorized": True})
    altered = trusted.model_copy(
        update={"source_groups": (altered_source, *trusted.source_groups[1:])}
    )

    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.evaluate_operator_f(altered)


def test_source_group_rejects_candidate_owned_quality_weight() -> None:
    payload = source_group(0).model_dump(mode="python")
    payload["blinded_quality_weight"] = 1.0

    with pytest.raises(ValueError):
        operator_f.OperatorFSourceGroup.model_validate(payload)


def test_replay_revalidates_typed_trusted_inputs() -> None:
    trusted = inputs(source_group(index) for index in range(5))
    result = operator_f.evaluate_operator_f(trusted)
    altered = trusted.model_copy(update={"imputation_authorized": True})

    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.validate_operator_f_evaluation_result(
            result.model_dump(mode="json"),
            trusted_inputs=altered,
        )


def test_candidate_owned_quality_scalar_cannot_authorize_metric() -> None:
    result = operator_f.evaluate_operator_f(inputs(source_group(index) for index in range(5)))

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert _metric(result, "quality_weighted_diversity").reason == (
        "missing_blinded_quality_weight"
    )


def test_duplicate_occupied_cell_quality_uses_one_maximum_weight_per_cell() -> None:
    ordered = records_in_fold_order(10)
    shared = operator_f.RegisteredCoordinates(mechanism="same", target="same", horizon="same")
    adjusted = tuple(
        record.model_copy(update={"registered_coordinates": shared}) if index in {0, 5} else record
        for index, record in enumerate(ordered)
    )
    trusted = inputs(
        adjusted,
        quality_reviews=tuple(quality_review(record) for record in adjusted),
    )

    result = operator_f.evaluate_operator_f(trusted)

    assert isinstance(result, operator_f.OperatorFReportResult)
    metric = _metric(result, "quality_weighted_diversity")
    assert metric.state == "available"
    assert metric.reason is None


@pytest.mark.parametrize("producer_field", ["producer_identity", "producer_session"])
def test_interpretability_review_colliding_with_any_source_producer_is_unavailable(
    producer_field: str,
) -> None:
    records = tuple(source_group(index) for index in range(10))
    reviews = interpretability_reviews(records)
    collision = records[0].provenance.model_dump()[producer_field]
    review_field = (
        "reviewer_identity" if producer_field == "producer_identity" else "reviewer_session"
    )
    altered_review = reviews[0].model_copy(update={review_field: collision})
    trusted = inputs(records, reviews=(altered_review, reviews[1]))

    result = operator_f.evaluate_operator_f(trusted)

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert _metric(result, "interpretability").reason == (
        "missing_independent_blinded_interpretability_rating"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("approved_source_byte_sha256", "f" * 64, "source digest"),
        ("reviewer_identity", "producer:0", "independent"),
        ("reviewer_session", "producer-session:0", "independent"),
        ("blinded_to_fold_assignment", False, "trusted inputs"),
        ("blinded_to_track_identity", False, "trusted inputs"),
        ("blinded_to_candidate_label", False, "trusted inputs"),
        ("blinded_to_numeric_outcomes", False, "trusted inputs"),
        ("completed_before_split_assignment", False, "trusted inputs"),
        ("weight", float("inf"), "trusted inputs"),
    ],
)
def test_quality_review_rejects_untrusted_binding(
    field: str,
    value: str | bool | float,
    message: str,
) -> None:
    records = tuple(source_group(index) for index in range(5))
    reviews = tuple(quality_review(record) for record in records)
    altered = reviews[0].model_copy(update={field: value})
    trusted = inputs(records).model_copy(
        update={"trusted_quality_reviews": (altered, *reviews[1:])}
    )

    with pytest.raises(ValueError, match=message):
        operator_f.evaluate_operator_f(trusted)


def test_duplicate_quality_review_is_rejected() -> None:
    records = tuple(source_group(index) for index in range(5))
    reviews = tuple(quality_review(record) for record in records)
    trusted = inputs(records).model_copy(update={"trusted_quality_reviews": (*reviews, reviews[0])})

    with pytest.raises(ValueError, match="duplicate trusted quality review"):
        operator_f.evaluate_operator_f(trusted)


@pytest.mark.parametrize("field", ["source_population_digest", "fold_assignment_digest"])
def test_interpretability_review_requires_current_source_and_fold_binding(field: str) -> None:
    records = tuple(source_group(index) for index in range(10))
    reviews = interpretability_reviews(records)
    altered = reviews[0].model_copy(update={field: "f" * 64})

    result = operator_f.evaluate_operator_f(inputs(records, reviews=(altered, reviews[1])))

    assert isinstance(result, operator_f.OperatorFReportResult)
    assert _metric(result, "interpretability").reason == (
        "missing_independent_blinded_interpretability_rating"
    )


@pytest.mark.parametrize(
    "field",
    [
        "blinded_to_source_identity",
        "blinded_to_fold_assignment",
        "blinded_to_numeric_outcomes",
    ],
)
def test_interpretability_review_requires_every_blinding(field: str) -> None:
    records = tuple(source_group(index) for index in range(10))
    reviews = interpretability_reviews(records)
    altered = reviews[0].model_copy(update={field: False})
    trusted = inputs(records).model_copy(update={"interpretability_reviews": (altered, reviews[1])})

    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.evaluate_operator_f(trusted)


def test_interpretability_review_requires_exact_predeclared_items() -> None:
    records = tuple(source_group(index) for index in range(10))
    reviews = interpretability_reviews(records)
    altered = reviews[0].model_copy(update={"predeclared_rating_items": ("different_item",)})
    trusted = inputs(records).model_copy(update={"interpretability_reviews": (altered, reviews[1])})

    with pytest.raises(ValueError, match="predeclared"):
        operator_f.evaluate_operator_f(trusted)
