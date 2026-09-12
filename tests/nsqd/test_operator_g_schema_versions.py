from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from nsqd.domain import contract_validation
from nsqd.domain.contract_validation import StructuredInput
from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    validate_operator_g_failure_contract,
    validate_operator_g_failure_record,
)
from nsqd.domain.operator_g_census import (
    CandidateClass,
    ReasonCode,
    RecordLocator,
    classify_failure_record,
)
from tests.nsqd.operator_dg_contract_support import operator_g_contract, operator_g_record
from tests.nsqd.operator_g_census_support import registered_record

REPO_ROOT = Path(__file__).resolve().parents[2]
V2_CONTRACT_PATH = (
    REPO_ROOT
    / "docs"
    / "reviews"
    / "nsqd-operator-g-failure-record-contract-2026-09-11-v2"
    / "failure-record-contract-v2.yaml"
)
V1_DIGEST = "094c42fb51da2d52154b5a4ca8c06bc89b7b0d33edd6e75dd99c24e6a7602b60"


def _v2_contract() -> dict[str, StructuredInput]:
    loaded: StructuredInput = yaml.safe_load(V2_CONTRACT_PATH.read_text(encoding="utf-8"))
    return contract_validation.as_mapping(loaded, "Operator G v2 contract fixture")


@pytest.mark.parametrize("review_status", ["pending", "rejected"])
def test_shipped_v1_record_remains_readable_digest_stable_and_ineligible(
    review_status: str,
) -> None:
    record = operator_g_record()
    review = contract_validation.mutable_mapping(record["review"])
    assert review is not None
    review["review_status"] = review_status

    validated = validate_operator_g_failure_record(record, contract=operator_g_contract())
    candidate = classify_failure_record(
        validated,
        locator=RecordLocator("legacy-v1.json#0"),
        contract=operator_g_contract(),
        trusted_approvals=frozenset(),
        trusted_evidence_artifacts=frozenset(),
        available_paths_by_digest={},
    )

    if review_status == "pending":
        assert operator_g_failure_record_digest(validated) == V1_DIGEST
    assert validated == record
    assert candidate.candidate_class is CandidateClass.PENDING
    assert candidate.reason_code is ReasonCode.UNAPPROVED
    assert candidate.qualifying is False


def test_v1_approved_record_cannot_gain_authority() -> None:
    record = operator_g_record()
    review = contract_validation.mutable_mapping(record["review"])
    assert review is not None
    review["review_status"] = "approved"
    review["human_reviewer"] = "human:reviewer"
    review["human_approved_at_utc"] = "2026-09-05T20:00:00Z"
    review["approved_record_digest"] = operator_g_failure_record_digest(record)

    with pytest.raises(ValueError, match="schema_version"):
        validate_operator_g_failure_record(record, contract=operator_g_contract())


@pytest.mark.parametrize(
    ("container", "field", "value", "message"),
    [
        ("original_conditions", "completed_at_utc", "2026-09-05T17:00:00Z", "precede"),
        ("outcome", "failure_class", "invented", "failure_class"),
        ("changed_condition_triggers", "resurrection_scope", "runtime", "resurrection_scope"),
        ("restart_conditions", "scope", "runtime", "restart condition scope"),
        ("review", "review_status", "invented", "review_status"),
        ("review", "human_reviewer", "human:metadata-only", "unapproved review"),
    ],
)
def test_v1_structural_validation_remains_fail_closed(
    container: str, field: str, value: StructuredInput, message: str
) -> None:
    record = operator_g_record()
    parent = record[container]
    if isinstance(parent, list):
        nested = contract_validation.mutable_mapping(parent[0])
    else:
        nested = contract_validation.mutable_mapping(parent)
    assert nested is not None
    nested[field] = value

    with pytest.raises(ValueError, match=message):
        validate_operator_g_failure_record(record, contract=operator_g_contract())


def test_expanded_v2_record_validates_against_standalone_contract() -> None:
    contract = _v2_contract()
    record = registered_record()

    assert validate_operator_g_failure_contract(contract)["schema_version"] == 2
    assert validate_operator_g_failure_record(record, contract=contract) == record


@pytest.mark.parametrize(
    "path",
    [
        ("scientific_purpose",),
        ("provenance", "producer_session"),
        ("review", "reviewer_session"),
        ("changed_condition_triggers", "measured_variable"),
        ("restart_conditions", "required_evidence_digest"),
    ],
)
def test_incomplete_v2_record_is_rejected(path: tuple[str, ...]) -> None:
    record = copy.deepcopy(registered_record())
    if len(path) == 1:
        del record[path[0]]
    else:
        parent = record[path[0]]
        if isinstance(parent, list):
            nested = contract_validation.mutable_mapping(parent[0])
        else:
            nested = contract_validation.mutable_mapping(parent)
        assert nested is not None
        del nested[path[1]]

    with pytest.raises(ValueError):
        validate_operator_g_failure_record(record, contract=_v2_contract())
