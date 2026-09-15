from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from papers.domain import InvestigationPlan, parse_investigation_plan_json
from papers.domain.investigation_renderer import render_investigation_plan_markdown
from tests.investigation_plan_test_data import valid_investigation_plan_payload


def test_plan_rejects_omitted_replication_and_resources() -> None:
    payload = valid_investigation_plan_payload()
    del payload["baseline_replication"]
    del payload["directions"][0]["compute"]

    with pytest.raises(ValidationError) as exc_info:
        InvestigationPlan.model_validate(payload)

    locations = {error["loc"] for error in exc_info.value.errors()}
    assert ("baseline_replication",) in locations
    assert ("directions", 0, "compute") in locations


@pytest.mark.parametrize("evidence_status", ["reported", "unknown"])
def test_plan_rejects_unsupported_evidence_claims(evidence_status: str) -> None:
    payload = valid_investigation_plan_payload()
    claim = payload["directions"][0]["data"]["access"]
    claim["evidence_status"] = evidence_status
    claim["source_refs"] = []
    claim["uncertainty_rationale"] = None

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_plan_rejects_unknown_claim_disguised_as_value() -> None:
    payload = valid_investigation_plan_payload()
    claim = payload["directions"][0]["data"]["license"]
    claim["value"] = "Probably research-only"

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_plan_rejects_numeric_estimate_without_basis_or_reported_citation() -> None:
    payload = valid_investigation_plan_payload()
    estimate = payload["directions"][0]["compute"]["gpu_hours"]
    estimate["evidence_status"] = "reported"
    estimate["basis"] = None
    estimate["source_refs"] = []

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_plan_rejects_non_finite_or_negative_compute_estimate() -> None:
    payload = valid_investigation_plan_payload()
    payload["directions"][0]["compute"]["gpu_hours"]["value"] = -1.0

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_plan_rejects_verified_step_without_execution_evidence() -> None:
    payload = valid_investigation_plan_payload()
    payload["baseline_replication"]["steps"][0]["status"] = "verified"

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_parse_and_render_provide_typed_renderer_handoff() -> None:
    payload = valid_investigation_plan_payload()

    plan = parse_investigation_plan_json(json.dumps(payload))
    markdown = render_investigation_plan_markdown(plan)

    assert isinstance(plan, InvestigationPlan)
    assert plan.baseline_replication.steps[0].status.value == "not_started"
    assert "## Baseline Replication" in markdown
    assert "## Investigation Directions" in markdown
    assert "not_started" in markdown


@pytest.mark.parametrize("placeholder", ["TBD", "todo", "N/A", "unknown", "None"])
def test_plan_rejects_reserved_whole_field_placeholders(placeholder: str) -> None:
    payload = valid_investigation_plan_payload()
    payload["baseline_replication"]["justification"] = placeholder

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_plan_rejects_empty_missing_information_without_supported_completeness() -> None:
    payload = valid_investigation_plan_payload()
    payload["baseline_replication"]["missing_information"] = []

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_plan_schema_exposes_replication_comparability_semantics() -> None:
    schema = InvestigationPlan.model_json_schema()
    baseline_schema = schema["$defs"]["BaselineReplication"]

    assert {
        "protocol_equivalence",
        "metric_comparability",
        "deviations",
        "comparison_scope",
    }.issubset(baseline_schema["properties"])


def test_provider_schema_requires_every_property_recursively() -> None:
    schema = InvestigationPlan.model_json_schema()

    object_schemas = [node for node in schema["$defs"].values() if node.get("type") == "object"] + [
        schema
    ]

    for object_schema in object_schemas:
        assert object_schema["additionalProperties"] is False
        assert set(object_schema["required"]) == set(object_schema["properties"])

    replication_step = schema["$defs"]["ReplicationStep"]
    blocked_reason_types = {
        option["type"] for option in replication_step["properties"]["blocked_reason"]["anyOf"]
    }
    assert blocked_reason_types == {"string", "null"}


@pytest.mark.parametrize("status", ["not_started", "verified"])
def test_replication_step_rejects_blocked_reason_unless_blocked(status: str) -> None:
    payload = valid_investigation_plan_payload()
    step = payload["baseline_replication"]["steps"][0]
    step["status"] = status
    step["blocked_reason"] = "This contradicts the selected status."
    if status == "verified":
        step["evidence_refs"] = ["run:1"]

    with pytest.raises(ValidationError, match="blocked reason"):
        InvestigationPlan.model_validate(payload)


@pytest.mark.parametrize("step_status", ["not_started", "blocked"])
def test_exact_target_allows_unknown_equivalence_without_direct_comparison(
    step_status: str,
) -> None:
    payload = valid_investigation_plan_payload()
    baseline = payload["baseline_replication"]
    baseline["strategy"] = "exact_replication"
    baseline["deviations"] = []
    baseline["steps"][0]["status"] = step_status
    baseline["steps"][0]["blocked_reason"] = (
        "Original checkpoint availability is unknown." if step_status == "blocked" else None
    )

    plan = InvestigationPlan.model_validate(payload)

    assert plan.baseline_replication.comparison_scope.value == "no_direct_comparison"


def test_exact_target_rejects_direct_metrics_when_equivalence_is_unknown() -> None:
    payload = valid_investigation_plan_payload()
    baseline = payload["baseline_replication"]
    baseline["strategy"] = "exact_replication"
    baseline["deviations"] = []
    baseline["comparison_scope"] = "direct_metrics"

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_constrained_reproduction_requires_explicit_substitution() -> None:
    payload = valid_investigation_plan_payload()
    payload["baseline_replication"]["deviations"] = []

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


@pytest.mark.parametrize(
    ("strategy", "comparison_scope"),
    [
        ("constrained_reproduction", "no_direct_comparison"),
        ("conceptual_reimplementation", "mechanism_only"),
    ],
)
def test_replication_strategy_rejects_unknown_deviation_as_substitution(
    strategy: str,
    comparison_scope: str,
) -> None:
    payload = valid_investigation_plan_payload()
    baseline = payload["baseline_replication"]
    baseline["strategy"] = strategy
    baseline["comparison_scope"] = comparison_scope
    baseline["deviations"] = [
        {
            "claim_kind": "fact",
            "evidence_status": "unknown",
            "value": None,
            "source_refs": [],
            "uncertainty_rationale": "The required substitution has not been selected.",
        }
    ]

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_conceptual_reimplementation_is_mechanism_only() -> None:
    payload = valid_investigation_plan_payload()
    baseline = payload["baseline_replication"]
    baseline["strategy"] = "conceptual_reimplementation"
    baseline["comparison_scope"] = "direct_metrics"

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


@pytest.mark.parametrize("sentinel", ["No missing information", "None identified"])
def test_missing_information_rejects_no_information_sentinel(sentinel: str) -> None:
    payload = valid_investigation_plan_payload()
    payload["baseline_replication"]["missing_information"] = [sentinel]

    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_empty_missing_information_requires_justified_complete_assessment() -> None:
    payload = valid_investigation_plan_payload()
    baseline = payload["baseline_replication"]
    baseline["missing_information"] = []
    baseline["information_completeness"] = {
        "evidence_status": "reported",
        "assessment": "complete",
        "source_refs": ["paper-1"],
        "uncertainty_rationale": None,
    }

    plan = InvestigationPlan.model_validate(payload)

    assert plan.baseline_replication.missing_information == ()
