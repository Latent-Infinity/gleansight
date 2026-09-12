from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from nsqd.domain.operator_approval import OperatorApprovalKind, TrustedOperatorApproval
from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    validate_operator_g_failure_record,
)
from nsqd.domain.operator_g_census import StructuredValue
from tests.nsqd.operator_dg_contract_support import operator_g_contract_v2
from tests.nsqd.operator_g_census_support import registered_record


def test_existing_valid_record_remains_report_only_and_ineligible() -> None:
    # Given: the valid pending Operator G protocol fixture
    record = registered_record()

    # When: it crosses the record-validation boundary
    validated = validate_operator_g_failure_record(record, contract=operator_g_contract_v2())

    # Then: technical validity grants neither eligibility nor authority
    assert validated["authorization_state"] == "report_only"
    assert validated["operator_g_eligible"] is False


def _approved_record() -> tuple[dict[str, StructuredValue], TrustedOperatorApproval]:
    record = registered_record()
    record["review"] = {
        "review_status": "approved",
        "human_reviewer": "human:g-reviewer",
        "reviewer_session": "session:g-reviewer",
        "human_approved_at_utc": "2026-09-05T19:00:00Z",
        "approval_scope": "operator_g_record_admission",
        "approved_record_digest": None,
    }
    digest = operator_g_failure_record_digest(record)
    review = record["review"]
    assert isinstance(review, dict)
    review["approved_record_digest"] = digest
    return record, TrustedOperatorApproval(
        OperatorApprovalKind.G_FAILURE_RECORD,
        digest,
        "human:g-reviewer",
        datetime(2026, 9, 5, 19, tzinfo=UTC),
        reviewer_session="session:g-reviewer",
        approval_scope="operator_g_record_admission",
    )


def _delete(record: dict[str, StructuredValue], path: tuple[str, ...]) -> None:
    selected = record
    for segment in path[:-1]:
        value = selected[segment]
        assert isinstance(value, dict)
        selected = value
    del selected[path[-1]]


@pytest.mark.parametrize(
    "path",
    [
        ("scientific_purpose",),
        ("registered_at_utc",),
        ("registration_digest",),
        ("exact_command",),
        ("resource_cap",),
        ("predeclared_success_failure_and_inconclusive_outcomes",),
        ("exit_status",),
        ("measured_outcome",),
        ("failure_classification",),
        ("cleanup_receipt",),
        ("provenance", "producer_session"),
        ("review", "reviewer_session"),
        ("review", "approval_scope"),
    ],
)
def test_frozen_record_field_deletion_fails_closed(path: tuple[str, ...]) -> None:
    # Given: a complete registered-experiment record missing one frozen field
    record = registered_record()
    _delete(record, path)

    # When/Then: validation rejects the incomplete record
    with pytest.raises(ValueError):
        validate_operator_g_failure_record(record, contract=operator_g_contract_v2())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scientific_purpose", " "),
        ("registered_at_utc", "not-utc"),
        ("registration_digest", "bad"),
        ("exact_command", ["not", "exact"]),
        ("resource_cap", {"wall_clock_seconds": 0}),
        ("predeclared_success_failure_and_inconclusive_outcomes", {"success": "only"}),
        ("exit_status", True),
        ("measured_outcome", {"loss": float("nan")}),
        ("failure_classification", "invented"),
        ("cleanup_receipt", "bad"),
    ],
)
def test_frozen_record_field_malformed_value_fails_closed(
    field: str, value: StructuredValue
) -> None:
    # Given: one malformed frozen boundary value
    record = registered_record()
    record[field] = value

    # When/Then: validation rejects it
    with pytest.raises(ValueError):
        validate_operator_g_failure_record(record, contract=operator_g_contract_v2())


@pytest.mark.parametrize(
    ("reviewer", "reviewer_session"),
    [
        ("agent:g-recorder", "session:different"),
        ("human:different", "session:g-producer"),
    ],
)
def test_reviewer_identity_and_session_must_each_differ_from_producer(
    reviewer: str, reviewer_session: str
) -> None:
    # Given: an approval colliding with one producer dimension
    record, _ = _approved_record()
    review = record["review"]
    assert isinstance(review, dict)
    review["human_reviewer"] = reviewer
    review["reviewer_session"] = reviewer_session
    review["approved_record_digest"] = operator_g_failure_record_digest(record)
    trusted = TrustedOperatorApproval(
        OperatorApprovalKind.G_FAILURE_RECORD,
        str(review["approved_record_digest"]),
        reviewer,
        datetime(2026, 9, 5, 19, tzinfo=UTC),
        reviewer_session=reviewer_session,
        approval_scope="operator_g_record_admission",
    )

    # When/Then: either collision rejects approval
    with pytest.raises(ValueError, match="independent"):
        validate_operator_g_failure_record(
            record, contract=operator_g_contract_v2(), trusted_approvals=frozenset({trusted})
        )


@pytest.mark.parametrize("field", ["reviewer_session", "approval_scope"])
def test_external_approval_requires_exact_session_and_scope_binding(field: str) -> None:
    # Given: valid record metadata with stale external trust in one binding dimension
    record, trusted = _approved_record()
    changes = {field: f"stale:{field}"}
    stale = TrustedOperatorApproval(
        trusted.kind,
        trusted.content_digest,
        trusted.reviewer_identity,
        trusted.approved_at_utc,
        reviewer_session=changes.get("reviewer_session", trusted.reviewer_session),
        approval_scope=changes.get("approval_scope", trusted.approval_scope),
    )

    # When/Then: tuple substitution cannot satisfy exact external trust
    with pytest.raises(ValueError, match="trusted approval"):
        validate_operator_g_failure_record(
            record, contract=operator_g_contract_v2(), trusted_approvals=frozenset({stale})
        )


def test_registration_digest_and_approval_digest_are_independent_bindings() -> None:
    # Given: changed registered purpose with only the later approval recomputed
    record, _ = _approved_record()
    record["scientific_purpose"] = "attacker changed the registered purpose"
    review = record["review"]
    assert isinstance(review, dict)
    review["approved_record_digest"] = operator_g_failure_record_digest(record)
    trusted = TrustedOperatorApproval(
        OperatorApprovalKind.G_FAILURE_RECORD,
        str(review["approved_record_digest"]),
        "human:g-reviewer",
        datetime(2026, 9, 5, 19, tzinfo=UTC),
        reviewer_session="session:g-reviewer",
        approval_scope="operator_g_record_admission",
    )

    # When/Then: stale pre-execution registration still rejects
    with pytest.raises(ValueError, match="registration_digest"):
        validate_operator_g_failure_record(
            record, contract=operator_g_contract_v2(), trusted_approvals=frozenset({trusted})
        )


def test_approval_must_follow_execution_completion() -> None:
    # Given: approval metadata predating completion
    record, _ = _approved_record()
    review = record["review"]
    assert isinstance(review, dict)
    review["human_approved_at_utc"] = "2026-09-05T18:15:00Z"
    review["approved_record_digest"] = operator_g_failure_record_digest(record)
    trusted = TrustedOperatorApproval(
        OperatorApprovalKind.G_FAILURE_RECORD,
        str(review["approved_record_digest"]),
        "human:g-reviewer",
        datetime(2026, 9, 5, 18, 15, tzinfo=UTC),
        reviewer_session="session:g-reviewer",
        approval_scope="operator_g_record_admission",
    )

    # When/Then: execution and review UTC ordering rejects it
    with pytest.raises(ValueError, match="approval.*completion"):
        validate_operator_g_failure_record(
            record, contract=operator_g_contract_v2(), trusted_approvals=frozenset({trusted})
        )


def test_every_governed_field_changes_the_canonical_digest() -> None:
    # Given: the complete frozen record and its canonical digest
    record = registered_record()
    original = operator_g_failure_record_digest(record)

    # When: each governed field is mutated independently
    for field in record:
        if field == "review":
            continue
        changed = copy.deepcopy(record)
        changed[field] = f"mutated:{field}"

        # Then: every governed field participates in the digest preimage
        assert operator_g_failure_record_digest(changed) != original
