from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import cast

import pytest

from nsqd.domain.contract_validation import StructuredInput
from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    validate_operator_g_failure_contract,
    validate_operator_g_failure_record,
)
from tests.nsqd.operator_dg_contract_support import (
    operator_g_contract_v2 as _contract,
)
from tests.nsqd.operator_g_census_support import registered_record as _record


def _record_value() -> dict[str, object]:
    return dict(_record())


_CANONICAL_FAILURE_CLASSES = [
    "implementation",
    "measurement",
    "method",
    "hypothesis",
    "regime_bound",
    "inconclusive",
]


def test_committed_operator_g_failure_contract_is_fail_closed() -> None:
    validated = validate_operator_g_failure_contract(_contract())
    assert validated["record_type"] == "approved_failed_experiment"
    assert validated["template_only"] is True
    assert validated["operator_g_eligible_by_default"] is False


def test_operator_g_failure_record_requires_evidence_bound_changed_conditions() -> None:
    validated = validate_operator_g_failure_record(_record_value(), contract=_contract())
    assert validated["operator_g_eligible"] is False
    assert len(operator_g_failure_record_digest(validated)) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("operator_g_eligible", True, "operator_g_eligible"),
        ("immutable_source_artifact_digests", [], "immutable_source_artifact_digests"),
        ("changed_condition_triggers", [], "changed_condition_triggers"),
        ("restart_conditions", [], "restart_conditions"),
    ],
)
def test_operator_g_failure_record_rejects_unsafe_or_incomplete_rows(
    field: str,
    value: StructuredInput,
    message: str,
) -> None:
    record = _record_value()
    record[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_record(record, contract=_contract())


def test_operator_g_failure_record_rejects_invented_or_self_approved_failure() -> None:
    invented = _record_value()
    outcome = cast(dict[str, object], copy.deepcopy(invented["outcome"]))
    outcome["measured_results"] = {}
    invented["outcome"] = outcome
    with pytest.raises(ValueError, match="measured_results"):
        validate_operator_g_failure_record(invented, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 1, "required_fields"),
        ("record_type", "other", "record_type"),
        ("template_only", False, "template_only"),
        ("operator_g_eligible_by_default", True, "ineligible"),
    ],
)
def test_operator_g_failure_contract_rejects_drift(
    field: str,
    value: StructuredInput,
    message: str,
) -> None:
    contract = _contract()
    contract[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_contract(contract)


def test_operator_g_failure_contract_rejects_source_class_widening() -> None:
    contract = _contract()
    source_classes = cast(list[str], contract["source_class_values"])
    source_classes.append("caller_added_source")

    with pytest.raises(ValueError, match="source_class_values"):
        validate_operator_g_failure_contract(contract)


def test_operator_g_failure_contract_rejects_runtime_resurrection_scope_widening() -> None:
    contract = _contract()
    resurrection_scopes = cast(list[str], contract["resurrection_scope_values"])
    resurrection_scopes.append("runtime")

    with pytest.raises(ValueError, match="resurrection_scope_values"):
        validate_operator_g_failure_contract(contract)


@pytest.mark.parametrize("mutation", ["deletion", "replacement", "widening", "duplication"])
def test_operator_g_rejects_caller_mutated_canonical_failure_classes(mutation: str) -> None:
    mutated = {
        "deletion": _CANONICAL_FAILURE_CLASSES[1:],
        "replacement": ["caller_failure"],
        "widening": [*_CANONICAL_FAILURE_CLASSES, "caller_failure"],
        "duplication": [*_CANONICAL_FAILURE_CLASSES, "implementation"],
    }[mutation]
    contract = _contract()
    contract["failure_class_values"] = mutated
    record = _record_value()
    outcome = cast(dict[str, object], record["outcome"])
    outcome["failure_class"] = "caller_failure" if mutation != "deletion" else "implementation"

    with pytest.raises(ValueError, match="failure_class_values"):
        validate_operator_g_failure_record(record, contract=contract)


@pytest.mark.parametrize("schema_version", [0, 3, True, 1.0, "1"])
def test_operator_g_contract_and_record_require_integer_schema_version(
    schema_version: StructuredInput,
) -> None:
    contract = _contract()
    contract["schema_version"] = schema_version
    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_g_failure_contract(contract)

    record = _record_value()
    record["schema_version"] = schema_version
    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_g_failure_record(record, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("immutable_source_artifact_digests", ("a" * 64,)),
        (
            "changed_condition_triggers",
            tuple(cast(list[object], _record_value()["changed_condition_triggers"])),
        ),
        ("restart_conditions", tuple(cast(list[object], _record_value()["restart_conditions"]))),
    ],
)
def test_operator_g_record_rejects_non_list_json_representations(
    field: str,
    value: object,
) -> None:
    record = _record_value()
    record[field] = value

    with pytest.raises(ValueError, match=field):
        validate_operator_g_failure_record(record, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("human_reviewer", "human:failure-reviewer"),
        ("human_approved_at_utc", "2026-09-05T20:00:00Z"),
        ("approved_record_digest", "0" * 64),
    ],
)
def test_operator_g_unapproved_failure_record_rejects_approval_fields(
    field: str,
    value: object,
) -> None:
    record = _record_value()
    review = cast(dict[str, object], record["review"])
    review[field] = value

    with pytest.raises(ValueError, match="unapproved review"):
        validate_operator_g_failure_record(record, contract=_contract())


def test_operator_g_failure_contract_and_nested_records_reject_extra_fields() -> None:
    contract = _contract()
    contract["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_operator_g_failure_contract(contract)

    record = _record_value()
    outcome = cast(dict[str, object], record["outcome"])
    outcome["unexpected"] = True
    with pytest.raises(ValueError, match="outcome fields"):
        validate_operator_g_failure_record(record, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 1, "schema_version"),
        ("authorization_state", "authorized", "authorization_state"),
        ("runtime_authorized", True, "fields do not match"),
        ("failure_record_id", " ", "failure_record_id"),
        ("source_class", "test_failure_without_experiment_evidence", "source_class"),
        ("source_class", "job_error_code", "source_class"),
        ("source_class", "sufficiency_failure", "source_class"),
        ("source_class", "inferred_or_invented_failure", "source_class"),
        ("source_class", "absence_of_published_or_successful_results", "source_class"),
        ("immutable_source_artifact_digests", ["BAD"], "sha256"),
    ],
)
def test_operator_g_failure_record_rejects_contract_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    record = _record_value()
    record[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_record(record, contract=_contract())


def test_operator_g_failure_record_rejects_invalid_time_class_scope_and_digest() -> None:
    reversed_time = _record_value()
    conditions = cast(dict[str, object], copy.deepcopy(reversed_time["original_conditions"]))
    conditions["completed_at_utc"] = "2026-09-05T17:00:00Z"
    reversed_time["original_conditions"] = conditions
    with pytest.raises(ValueError, match="must not precede"):
        validate_operator_g_failure_record(reversed_time, contract=_contract())

    invalid_class = _record_value()
    outcome = cast(dict[str, object], copy.deepcopy(invalid_class["outcome"]))
    outcome["failure_class"] = "missing_success"
    invalid_class["outcome"] = outcome
    with pytest.raises(ValueError, match="failure_class"):
        validate_operator_g_failure_record(invalid_class, contract=_contract())

    invalid_scope = _record_value()
    triggers = cast(
        list[dict[str, object]], copy.deepcopy(invalid_scope["changed_condition_triggers"])
    )
    triggers[0]["resurrection_scope"] = "runtime"
    invalid_scope["changed_condition_triggers"] = triggers
    with pytest.raises(ValueError, match="resurrection_scope"):
        validate_operator_g_failure_record(invalid_scope, contract=_contract())

    invalid_restart = _record_value()
    restarts = cast(list[dict[str, object]], copy.deepcopy(invalid_restart["restart_conditions"]))
    restarts[0]["scope"] = "runtime"
    invalid_restart["restart_conditions"] = restarts
    with pytest.raises(ValueError, match="restart condition scope"):
        validate_operator_g_failure_record(invalid_restart, contract=_contract())

    for invalid_result in (float("nan"), float("inf"), "unmeasured"):
        invalid_measured = _record_value()
        outcome = cast(dict[str, object], invalid_measured["outcome"])
        outcome["measured_results"] = {"validation_loss": invalid_result}
        with pytest.raises(ValueError, match="finite numeric"):
            validate_operator_g_failure_record(invalid_measured, contract=_contract())


def test_operator_g_failure_record_rejects_malformed_shapes() -> None:
    with pytest.raises(ValueError, match="string-keyed mapping"):
        validate_operator_g_failure_record(
            cast(Mapping[str, object], "not-a-mapping"),
            contract=_contract(),
        )
    extra = _record_value()
    extra["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_operator_g_failure_record(extra, contract=_contract())
    duplicate = _record_value()
    duplicate["immutable_source_artifact_digests"] = ["a" * 64, "a" * 64]
    with pytest.raises(ValueError, match="unique"):
        validate_operator_g_failure_record(duplicate, contract=_contract())
    malformed_triggers = _record_value()
    malformed_triggers["changed_condition_triggers"] = "trigger"
    with pytest.raises(ValueError, match="non-empty list"):
        validate_operator_g_failure_record(malformed_triggers, contract=_contract())
