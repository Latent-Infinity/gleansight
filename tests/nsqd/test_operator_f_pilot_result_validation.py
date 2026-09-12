from __future__ import annotations

import json

import pytest

import nsqd.domain.operator_f_pilot as operator_f
from tests.nsqd.operator_f_pilot_support import (
    _inputs,
    canonical_result_digest,
    historical_operator_f_inputs,
)


def test_pilot_result_validation_fails_closed_after_shape_or_digest_tampering() -> None:
    # Given a valid evaluator-produced result mapping
    result = operator_f.evaluate_operator_f_pilot(_inputs())
    payload = result.model_dump(mode="json")

    # When an unknown field or metric is introduced
    extra = dict(payload)
    extra["unexpected"] = True
    changed = json.loads(json.dumps(payload))
    changed["tracks"][0]["occupied_cell_count"] = 4

    # Then exact-shape and canonical digest checks reject both mutations
    with pytest.raises(ValueError, match="result shape"):
        operator_f.validate_operator_f_pilot_result(extra, trusted_inputs=_inputs())
    with pytest.raises(ValueError, match="result digest"):
        operator_f.validate_operator_f_pilot_result(changed, trusted_inputs=_inputs())

    recomputed = result.model_dump(mode="json")
    recomputed["findings"] = ["tampered finding"]
    recomputed["result_digest"] = canonical_result_digest(recomputed)
    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.validate_operator_f_pilot_result(recomputed, trusted_inputs=_inputs())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("records", 0, "record_id"), " "),
        (("records", 1, "registered_coordinates", "mechanism"), " "),
        (("records", 1, "registered_coordinates", "target"), ""),
        (("records", 1, "registered_coordinates", "horizon"), "\t"),
    ],
)
def test_pilot_result_rejects_blank_identifiers_and_coordinate_components(
    path: tuple[str | int, ...],
    value: operator_f.JsonValue,
) -> None:
    payload = operator_f.evaluate_operator_f_pilot(_inputs()).model_dump(mode="json")
    target: dict[str, operator_f.JsonValue] | list[operator_f.JsonValue] = payload
    for component in path[:-1]:
        if isinstance(target, dict):
            assert isinstance(component, str)
            child = target[component]
        else:
            assert isinstance(component, int)
            child = target[component]
        assert isinstance(child, dict | list)
        target = child
    final_component = path[-1]
    if isinstance(target, dict):
        assert isinstance(final_component, str)
        target[final_component] = value
    else:
        assert isinstance(final_component, int)
        target[final_component] = value

    with pytest.raises(ValueError, match="result shape"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=_inputs())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "1"),
        ("total_record_count", True),
        ("candidate_observed_record_count", 5.0),
    ],
)
def test_pilot_result_rejects_numeric_scalar_coercions(
    field: str,
    value: operator_f.JsonValue,
) -> None:
    inputs = _inputs()
    payload = operator_f.evaluate_operator_f_pilot(inputs).model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValueError, match="result shape"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=inputs)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_pilot_result_rejects_nonfinite_metrics(value: float) -> None:
    inputs = _inputs()
    payload = operator_f.evaluate_operator_f_pilot(inputs).model_dump(mode="json")
    payload["tracks"][0]["observed_cell_coverage"] = value
    payload["result_digest"] = canonical_result_digest(payload)

    with pytest.raises(ValueError, match="result shape"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=inputs)


def test_pilot_result_rejects_integer_metric_coercion() -> None:
    inputs = _inputs()
    payload = operator_f.evaluate_operator_f_pilot(inputs).model_dump(mode="json")
    payload["tracks"][0]["observed_cell_coverage"] = 1

    with pytest.raises(ValueError, match="result shape"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=inputs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runtime_authorized", 0),
        ("schema_mutation_authorized", 0.0),
        ("schema_admission_authorized", "false"),
        ("evidence_sufficient", 0),
        ("schema_admission_recommended", 0),
    ],
)
def test_pilot_result_rejects_boolean_substitutes(
    field: str,
    value: operator_f.JsonValue,
) -> None:
    inputs = _inputs()
    payload = operator_f.evaluate_operator_f_pilot(inputs).model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValueError, match="result shape"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=inputs)


@pytest.mark.parametrize(
    "substitution",
    [
        "proposal",
        "approved_digest",
        "snapshot",
        "record",
        "projection",
        "coordinate",
        "label",
        "source_path",
        "source_digest",
        "shuffle",
    ],
)
def test_pilot_result_rejects_self_consistent_semantic_substitutions(
    substitution: str,
) -> None:
    trusted = historical_operator_f_inputs()
    data = trusted.model_dump(mode="python")
    if substitution == "proposal":
        data["proposal_id"] = "F-PROP-OTHER"
    elif substitution == "approved_digest":
        data["approved_proposal_digest"] = "f" * 64
    elif substitution == "snapshot":
        data["source_snapshot_id"] = "f" * 64
    elif substitution == "record":
        data["records"][0]["record_id"] = "N11-FIN-OTHER"
    elif substitution == "projection":
        data["records"][0]["projection_sha256"] = "f" * 64
        data["source_artifacts"][4]["sha256"] = "f" * 64
    elif substitution == "coordinate":
        data["records"][1]["registered_coordinates"]["mechanism"] = "flow-driven"
    elif substitution == "label":
        data["records"][0]["validation_target"] = "calibrated_risk"
    elif substitution == "source_path":
        data["source_artifacts"][0]["path"] = "other-contract.yaml"
    elif substitution == "source_digest":
        data["source_artifacts"][0]["sha256"] = "f" * 64
    elif substitution == "shuffle":
        data["shuffle_seed"] = "other-seed"
    submitted_inputs = operator_f.OperatorFPilotInputs.model_validate(data)
    payload = operator_f.evaluate_operator_f_pilot(submitted_inputs).model_dump(mode="json")

    with pytest.raises(ValueError, match="trusted inputs"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=trusted)


def test_pilot_result_rejects_valid_result_digest_substitution() -> None:
    trusted = historical_operator_f_inputs()
    payload = operator_f.evaluate_operator_f_pilot(trusted).model_dump(mode="json")
    payload["result_digest"] = "f" * 64

    with pytest.raises(ValueError, match="result digest"):
        operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=trusted)
