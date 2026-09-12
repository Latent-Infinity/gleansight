from __future__ import annotations

import ast
import copy
from collections.abc import Callable
from pathlib import Path

import pytest

from nsqd.domain.contract_validation import StructuredValue
from nsqd.domain.contract_validation_errors import (
    ContractValidationError,
    ContractValidationReason,
)
from nsqd.domain.operator_d import (
    operator_d_mapping_proposal_digest,
    validate_operator_d_mapping_proposal,
)
from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    operator_g_registration_digest,
    validate_changed_and_restart_conditions,
    validate_execution_outcome,
    validate_operator_g_failure_record,
    validate_registration,
)
from tests.nsqd.operator_dg_contract_support import (
    operator_d_contract,
    operator_d_proposal,
    operator_g_contract,
    operator_g_contract_v2,
    operator_g_record,
)
from tests.nsqd.operator_g_census_support import registered_record

_D_DIGEST = "cca1c3b7b498326f6106867ccaa3e288f2122b23fd034eaa75fc4cacf02e2ba7"
_G_DIGEST = "094c42fb51da2d52154b5a4ca8c06bc89b7b0d33edd6e75dd99c24e6a7602b60"


def test_operator_g_facade_preserves_release_validation_exports() -> None:
    assert callable(operator_g_registration_digest)
    assert callable(validate_registration)
    assert callable(validate_execution_outcome)
    assert callable(validate_changed_and_restart_conditions)


def test_validation_preserves_registration_digest_bytes() -> None:
    # Given
    proposal = operator_d_proposal()

    # When
    validated = validate_operator_d_mapping_proposal(proposal, contract=operator_d_contract())

    # Then
    assert operator_d_mapping_proposal_digest(validated) == _D_DIGEST


def test_validation_preserves_failure_record_digest_bytes() -> None:
    # Given
    legacy_record = operator_g_record()
    record = registered_record()
    original_digest = operator_g_failure_record_digest(record)

    # When
    validated = validate_operator_g_failure_record(record, contract=operator_g_contract_v2())

    # Then
    assert operator_g_failure_record_digest(legacy_record) == _G_DIGEST
    assert operator_g_failure_record_digest(validated) == original_digest


@pytest.mark.parametrize(
    ("validator", "payload", "contract", "message"),
    [
        (
            validate_operator_d_mapping_proposal,
            operator_d_proposal,
            operator_d_contract,
            "authorization_state must be report_only",
        ),
        (
            validate_operator_g_failure_record,
            registered_record,
            operator_g_contract_v2,
            "authorization_state must be report_only",
        ),
    ],
)
def test_validation_preserves_exact_first_error_and_precedence(
    validator: Callable[..., dict[str, StructuredValue]],
    payload: Callable[[], dict[str, StructuredValue]],
    contract: Callable[[], dict[str, StructuredValue]],
    message: str,
) -> None:
    # Given
    candidate = payload()
    candidate["authorization_state"] = "authorized"
    if "runtime_authorized" in candidate:
        candidate["runtime_authorized"] = True
    else:
        candidate["operator_g_eligible"] = True

    # When
    with pytest.raises(ValueError) as raised:
        validator(candidate, contract=contract())

    # Then
    assert str(raised.value) == message


def test_contract_validation_precedes_failure_record_validation() -> None:
    # Given
    contract = operator_g_contract()
    contract["record_type"] = "other"
    record = operator_g_record()
    record["authorization_state"] = "authorized"

    # When
    with pytest.raises(ValueError) as raised:
        validate_operator_g_failure_record(record, contract=contract)

    # Then
    assert str(raised.value) == "Operator G failure contract record_type is invalid"


def test_contract_errors_expose_typed_reason_and_field_while_remaining_value_errors() -> None:
    # Given
    contract = operator_g_contract()
    contract["record_type"] = "other"

    # When
    with pytest.raises(ContractValidationError) as raised:
        validate_operator_g_failure_record(operator_g_record(), contract=contract)

    # Then
    assert isinstance(raised.value, ValueError)
    assert raised.value.reason is ContractValidationReason.INVALID_VALUE
    assert raised.value.field == "Operator G failure contract record_type"
    assert str(raised.value) == "Operator G failure contract record_type is invalid"


@pytest.mark.parametrize(
    ("validator", "payload", "contract"),
    [
        (validate_operator_d_mapping_proposal, operator_d_proposal, operator_d_contract),
        (validate_operator_g_failure_record, registered_record, operator_g_contract_v2),
    ],
)
def test_validation_does_not_mutate_inputs(
    validator: Callable[..., dict[str, StructuredValue]],
    payload: Callable[[], dict[str, StructuredValue]],
    contract: Callable[[], dict[str, StructuredValue]],
) -> None:
    # Given
    candidate = payload()
    rules = contract()
    original_candidate = copy.deepcopy(candidate)
    original_rules = copy.deepcopy(rules)

    # When
    validator(candidate, contract=rules)

    # Then
    assert candidate == original_candidate
    assert rules == original_rules


def test_fixture_values_are_structurally_equal_but_independent() -> None:
    # Given
    first = operator_g_record()
    second = operator_g_record()

    # When
    first["failure_record_id"] = "changed"

    # Then
    assert second == operator_g_record()
    assert first != second
    assert first is not second
    assert first["review"] is not second["review"]


def test_operator_g_fixture_remains_visible_to_ast_classification() -> None:
    # Given
    support_path = Path(__file__).with_name("operator_dg_contract_support.py")

    # When
    tree = ast.parse(support_path.read_text(encoding="utf-8"), filename=str(support_path))
    fixtures = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "operator_g_record"
    ]

    # Then
    assert len(fixtures) == 1
