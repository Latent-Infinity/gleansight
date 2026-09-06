from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    validate_operator_g_failure_contract,
    validate_operator_g_failure_record,
)

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reviews"
    / "nsqd-operator-activation-2026-08-30"
    / "failure-record-contract.yaml"
)


def _contract() -> dict[str, object]:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _record() -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": 1,
        "failure_record_id": "G-FAIL-001",
        "authorization_state": "report_only",
        "operator_g_eligible": False,
        "domain_policy_id": "finance/1",
        "experiment_id": "experiment-001",
        "source_class": "registered_experiment_artifact",
        "immutable_source_artifact_digests": ["a" * 64],
        "original_conditions": {
            "code_revision": "b" * 40,
            "data_snapshot_ids": ["c" * 64],
            "configuration_digest": "d" * 64,
            "model_or_method_identity": "forecast-model/1",
            "started_at_utc": "2026-09-05T18:00:00Z",
            "completed_at_utc": "2026-09-05T18:30:00Z",
        },
        "outcome": {
            "failure_class": "method",
            "bounded_observation": "Validation loss exceeded the registered baseline.",
            "measured_results": {"validation_loss": 1.2, "baseline_loss": 1.0},
            "evidence_artifact_digests": ["e" * 64],
        },
        "changed_condition_triggers": [
            {
                "trigger_id": "trigger-001",
                "predicate": "data regime changes from calm to stress",
                "previous_condition": "calm",
                "new_condition": "stress",
                "evidence_artifact_digests": ["f" * 64],
                "resurrection_scope": "test_only",
            }
        ],
        "restart_conditions": [
            {
                "condition_id": "restart-001",
                "predicate": "stress benchmark is available",
                "scope": "test_only",
            }
        ],
        "provenance": {"generated_by": "agent:g-recorder"},
        "review": {
            "review_status": "pending",
            "human_reviewer": None,
            "human_approved_at_utc": None,
            "approved_record_digest": None,
        },
    }
    return record


def test_committed_operator_g_failure_contract_is_fail_closed() -> None:
    validated = validate_operator_g_failure_contract(_contract())
    assert validated["record_type"] == "approved_failed_experiment"
    assert validated["template_only"] is True
    assert validated["operator_g_eligible_by_default"] is False


def test_operator_g_failure_record_requires_evidence_bound_changed_conditions() -> None:
    validated = validate_operator_g_failure_record(_record(), contract=_contract())
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
    value: object,
    message: str,
) -> None:
    record = _record()
    record[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_record(record, contract=_contract())


def test_operator_g_failure_record_rejects_invented_or_self_approved_failure() -> None:
    invented = _record()
    outcome = cast(dict[str, object], copy.deepcopy(invented["outcome"]))
    outcome["measured_results"] = {}
    invented["outcome"] = outcome
    with pytest.raises(ValueError, match="measured_results"):
        validate_operator_g_failure_record(invented, contract=_contract())

    approved = _record()
    digest = operator_g_failure_record_digest(approved)
    approved["review"] = {
        "review_status": "approved",
        "human_reviewer": "agent:g-recorder",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approved_record_digest": digest,
    }
    with pytest.raises(ValueError, match="independent human"):
        validate_operator_g_failure_record(approved, contract=_contract())

    agent_approved = _record()
    agent_approved["review"] = {
        "review_status": "approved",
        "human_reviewer": "agent:independent-reviewer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approved_record_digest": None,
    }
    review = cast(dict[str, object], agent_approved["review"])
    review["approved_record_digest"] = operator_g_failure_record_digest(agent_approved)
    with pytest.raises(ValueError, match="human reviewer"):
        validate_operator_g_failure_record(agent_approved, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema_version"),
        ("record_type", "other", "record_type"),
        ("template_only", False, "template_only"),
        ("operator_g_eligible_by_default", True, "ineligible"),
    ],
)
def test_operator_g_failure_contract_rejects_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    contract = _contract()
    contract[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_contract(contract)


def test_operator_g_failure_contract_and_nested_records_reject_extra_fields() -> None:
    contract = _contract()
    contract["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_operator_g_failure_contract(contract)

    record = _record()
    outcome = cast(dict[str, object], record["outcome"])
    outcome["unexpected"] = True
    with pytest.raises(ValueError, match="outcome fields"):
        validate_operator_g_failure_record(record, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema_version"),
        ("authorization_state", "authorized", "authorization_state"),
        ("failure_record_id", " ", "failure_record_id"),
        ("source_class", "test_failure_without_experiment_evidence", "source_class"),
        ("immutable_source_artifact_digests", ["BAD"], "sha256"),
    ],
)
def test_operator_g_failure_record_rejects_contract_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    record = _record()
    record[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_record(record, contract=_contract())


def test_operator_g_failure_record_rejects_invalid_time_class_scope_and_digest() -> None:
    reversed_time = _record()
    conditions = cast(dict[str, object], copy.deepcopy(reversed_time["original_conditions"]))
    conditions["completed_at_utc"] = "2026-09-05T17:00:00Z"
    reversed_time["original_conditions"] = conditions
    with pytest.raises(ValueError, match="must not precede"):
        validate_operator_g_failure_record(reversed_time, contract=_contract())

    invalid_class = _record()
    outcome = cast(dict[str, object], copy.deepcopy(invalid_class["outcome"]))
    outcome["failure_class"] = "missing_success"
    invalid_class["outcome"] = outcome
    with pytest.raises(ValueError, match="failure_class"):
        validate_operator_g_failure_record(invalid_class, contract=_contract())

    invalid_scope = _record()
    triggers = cast(
        list[dict[str, object]], copy.deepcopy(invalid_scope["changed_condition_triggers"])
    )
    triggers[0]["resurrection_scope"] = "runtime"
    invalid_scope["changed_condition_triggers"] = triggers
    with pytest.raises(ValueError, match="resurrection_scope"):
        validate_operator_g_failure_record(invalid_scope, contract=_contract())

    invalid_restart = _record()
    restarts = cast(list[dict[str, object]], copy.deepcopy(invalid_restart["restart_conditions"]))
    restarts[0]["scope"] = "runtime"
    invalid_restart["restart_conditions"] = restarts
    with pytest.raises(ValueError, match="restart condition scope"):
        validate_operator_g_failure_record(invalid_restart, contract=_contract())

    for invalid_result in (float("nan"), float("inf"), "unmeasured"):
        invalid_measured = _record()
        outcome = cast(dict[str, object], invalid_measured["outcome"])
        outcome["measured_results"] = {"validation_loss": invalid_result}
        with pytest.raises(ValueError, match="finite numeric"):
            validate_operator_g_failure_record(invalid_measured, contract=_contract())


def test_operator_g_failure_record_accepts_independent_digest_bound_review() -> None:
    approved = _record()
    approved["review"] = {
        "review_status": "approved",
        "human_reviewer": "human:failure-reviewer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approved_record_digest": None,
    }
    review = cast(dict[str, object], approved["review"])
    review["approved_record_digest"] = operator_g_failure_record_digest(approved)
    assert validate_operator_g_failure_record(approved, contract=_contract())["review"] == review

    invalid_digest = copy.deepcopy(approved)
    invalid_review = cast(dict[str, object], invalid_digest["review"])
    invalid_review["approved_record_digest"] = "0" * 64
    with pytest.raises(ValueError, match="approved_record_digest"):
        validate_operator_g_failure_record(invalid_digest, contract=_contract())

    invalid_time = copy.deepcopy(approved)
    invalid_review = cast(dict[str, object], invalid_time["review"])
    invalid_review["human_approved_at_utc"] = "not-a-date"
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        validate_operator_g_failure_record(invalid_time, contract=_contract())


def test_operator_g_failure_record_rejects_malformed_shapes() -> None:
    with pytest.raises(ValueError, match="string-keyed mapping"):
        validate_operator_g_failure_record(
            cast(Mapping[str, object], "not-a-mapping"),
            contract=_contract(),
        )
    extra = _record()
    extra["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_operator_g_failure_record(extra, contract=_contract())
    duplicate = _record()
    duplicate["immutable_source_artifact_digests"] = ["a" * 64, "a" * 64]
    with pytest.raises(ValueError, match="unique"):
        validate_operator_g_failure_record(duplicate, contract=_contract())
    malformed_triggers = _record()
    malformed_triggers["changed_condition_triggers"] = "trigger"
    with pytest.raises(ValueError, match="non-empty list"):
        validate_operator_g_failure_record(malformed_triggers, contract=_contract())
