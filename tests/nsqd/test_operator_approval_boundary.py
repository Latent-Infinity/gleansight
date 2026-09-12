from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest

from nsqd.domain.contract_validation import StructuredInput, StructuredValue
from nsqd.domain.operator_approval import (
    OperatorApprovalKind,
    TrustedOperatorApproval,
    require_operator_d_approval,
    require_operator_g_approval,
)
from nsqd.domain.operator_d import validate_operator_d_mapping_proposal
from nsqd.domain.operator_g import (
    operator_g_registration_digest,
    validate_operator_g_failure_record,
)
from tests.nsqd.operator_dg_contract_support import (
    operator_d_contract,
    operator_d_proposal,
    operator_g_contract_v2,
)
from tests.nsqd.operator_g_census_support import registered_record


@dataclass(frozen=True, slots=True)
class _OperatorCase:
    kind: OperatorApprovalKind
    digest_field: str
    status_field: str
    approved_status: str
    payload: Callable[[], dict[str, StructuredInput]]
    contract: Callable[[], dict[str, StructuredInput]]
    validate: Callable[
        [
            Mapping[str, StructuredInput],
            Mapping[str, StructuredInput],
            frozenset[TrustedOperatorApproval],
        ],
        dict[str, StructuredValue],
    ]


def _validate_d(
    payload: Mapping[str, StructuredInput],
    contract: Mapping[str, StructuredInput],
    trusted: frozenset[TrustedOperatorApproval],
) -> dict[str, StructuredValue]:
    return validate_operator_d_mapping_proposal(
        payload, contract=contract, trusted_approvals=trusted
    )


def _validate_g(
    payload: Mapping[str, StructuredInput],
    contract: Mapping[str, StructuredInput],
    trusted: frozenset[TrustedOperatorApproval],
) -> dict[str, StructuredValue]:
    return validate_operator_g_failure_record(payload, contract=contract, trusted_approvals=trusted)


D_CASE = _OperatorCase(
    OperatorApprovalKind.D_MAPPING_PROPOSAL,
    "approved_proposal_digest",
    "status",
    "human_approved",
    operator_d_proposal,
    operator_d_contract,
    _validate_d,
)
G_CASE = _OperatorCase(
    OperatorApprovalKind.G_FAILURE_RECORD,
    "approved_record_digest",
    "review_status",
    "approved",
    registered_record,
    operator_g_contract_v2,
    _validate_g,
)
CASES = (D_CASE, G_CASE)


def _approval_digest(payload: Mapping[str, StructuredInput], *, field: str) -> str:
    preimage = copy.deepcopy(payload)
    review = cast(dict[str, object], preimage["review"])
    review[field] = None
    serialized = json.dumps(
        preimage,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _approved(case: _OperatorCase) -> dict[str, StructuredInput]:
    payload = case.payload()
    payload["review"] = {
        case.status_field: case.approved_status,
        "human_reviewer": "human:trusted-reviewer",
        **(
            {
                "reviewer_session": "session:trusted-reviewer",
                "approval_scope": "operator_g_record_admission",
            }
            if case is G_CASE
            else {}
        ),
        "human_approved_at_utc": "2026-09-08T12:00:00Z",
        case.digest_field: None,
    }
    review = cast(dict[str, object], payload["review"])
    review[case.digest_field] = _approval_digest(payload, field=case.digest_field)
    return payload


def _trusted(
    case: _OperatorCase, payload: Mapping[str, StructuredInput]
) -> TrustedOperatorApproval:
    review = cast(Mapping[str, object], payload["review"])
    return TrustedOperatorApproval(
        kind=case.kind,
        content_digest=cast(str, review[case.digest_field]),
        reviewer_identity=cast(str, review["human_reviewer"]),
        approved_at_utc=datetime.fromisoformat(
            cast(str, review["human_approved_at_utc"]).replace("Z", "+00:00")
        ),
        reviewer_session=(cast(str, review["reviewer_session"]) if case is G_CASE else None),
        approval_scope=(cast(str, review["approval_scope"]) if case is G_CASE else None),
    )


@pytest.mark.parametrize("case", CASES)
def test_approved_metadata_requires_independently_supplied_trust(case: _OperatorCase) -> None:
    payload = _approved(case)
    review = cast(dict[str, object], payload["review"])
    review["human_reviewer"] = "human:attacker-chosen-identity"
    review[case.digest_field] = _approval_digest(payload, field=case.digest_field)

    with pytest.raises(ValueError, match="trusted approval"):
        case.validate(payload, case.contract(), frozenset())
    with pytest.raises(ValueError, match="trusted approval"):
        if case.kind is OperatorApprovalKind.D_MAPPING_PROPOSAL:
            validate_operator_d_mapping_proposal(payload, contract=case.contract())
        else:
            validate_operator_g_failure_record(payload, contract=case.contract())


@pytest.mark.parametrize("case", CASES)
def test_exact_trusted_tuple_accepts_report_only_metadata(case: _OperatorCase) -> None:
    payload = _approved(case)

    validated = case.validate(payload, case.contract(), frozenset({_trusted(case, payload)}))

    assert validated["authorization_state"] == "report_only"
    assert validated["review"] == payload["review"]
    if case.kind is OperatorApprovalKind.D_MAPPING_PROPOSAL:
        assert validated["runtime_authorized"] is False
        assert validated["candidate_inferences"] == []
        assert validated["upstream_c"] == {
            "evidence_sufficient": False,
            "human_accepted": False,
            "selected_bridge_id": None,
        }
    else:
        assert validated["operator_g_eligible"] is False
        triggers = cast(list[dict[str, object]], validated["changed_condition_triggers"])
        restarts = cast(list[dict[str, object]], validated["restart_conditions"])
        assert triggers[0]["resurrection_scope"] == "test_only"
        assert restarts[0]["scope"] == "test_only"


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("wrong_field", ["kind", "reviewer", "time"])
def test_trust_tuple_requires_exact_kind_reviewer_and_instant(
    case: _OperatorCase, wrong_field: str
) -> None:
    payload = _approved(case)
    trusted = _trusted(case, payload)
    wrong_kind = (
        OperatorApprovalKind.G_FAILURE_RECORD
        if case.kind is OperatorApprovalKind.D_MAPPING_PROPOSAL
        else OperatorApprovalKind.D_MAPPING_PROPOSAL
    )
    candidate = TrustedOperatorApproval(
        kind=wrong_kind if wrong_field == "kind" else trusted.kind,
        content_digest=trusted.content_digest,
        reviewer_identity=(
            "human:different-reviewer" if wrong_field == "reviewer" else trusted.reviewer_identity
        ),
        approved_at_utc=(
            trusted.approved_at_utc + timedelta(seconds=1)
            if wrong_field == "time"
            else trusted.approved_at_utc
        ),
    )

    with pytest.raises(ValueError, match="trusted approval"):
        case.validate(payload, case.contract(), frozenset({candidate}))


@pytest.mark.parametrize("case", CASES)
def test_content_mutation_with_recomputed_digest_rejects_old_trust(case: _OperatorCase) -> None:
    payload = _approved(case)
    trusted = _trusted(case, payload)
    mutation_field = "proposal_id" if case is D_CASE else "failure_record_id"
    payload[mutation_field] = "attacker-mutated-id"
    if case is G_CASE:
        payload["registration_digest"] = operator_g_registration_digest(payload)
    review = cast(dict[str, object], payload["review"])
    review[case.digest_field] = _approval_digest(payload, field=case.digest_field)

    with pytest.raises(ValueError, match="trusted approval"):
        case.validate(payload, case.contract(), frozenset({trusted}))


@pytest.mark.parametrize("case", CASES)
def test_content_mutation_without_recomputed_digest_fails_integrity(case: _OperatorCase) -> None:
    payload = _approved(case)
    trusted = _trusted(case, payload)
    mutation_field = "proposal_id" if case is D_CASE else "failure_record_id"
    payload[mutation_field] = "attacker-mutated-id"
    if case is G_CASE:
        payload["registration_digest"] = operator_g_registration_digest(payload)

    with pytest.raises(ValueError, match=case.digest_field):
        case.validate(payload, case.contract(), frozenset({trusted}))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_unapproved_null_review_accepts_without_trust(case: _OperatorCase, status: str) -> None:
    payload = case.payload()
    review = cast(dict[str, object], payload["review"])
    review[case.status_field] = status

    assert case.validate(payload, case.contract(), frozenset())["review"] == review


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("status", ["pending", "rejected"])
@pytest.mark.parametrize("field", ["human_reviewer", "human_approved_at_utc", "approved digest"])
def test_unapproved_populated_review_rejects_without_trust(
    case: _OperatorCase, status: str, field: str
) -> None:
    payload = case.payload()
    review = cast(dict[str, object], payload["review"])
    review[case.status_field] = status
    selected_field = case.digest_field if field == "approved digest" else field
    review[selected_field] = "a" * 64 if field == "approved digest" else "human:unexpected"

    with pytest.raises(ValueError, match="unapproved review"):
        case.validate(payload, case.contract(), frozenset())


@pytest.mark.parametrize("case", CASES)
def test_submitted_reviewer_identity_rejects_whitespace_normalization(case: _OperatorCase) -> None:
    payload = _approved(case)
    review = cast(dict[str, object], payload["review"])
    review["human_reviewer"] = " human:trusted-reviewer"
    review[case.digest_field] = _approval_digest(payload, field=case.digest_field)

    with pytest.raises(ValueError, match="nonblank exact identity"):
        case.validate(payload, case.contract(), frozenset())


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    ("reviewer", "message"),
    [("agent:d-proposer", "independent human"), ("agent:reviewer", "human reviewer identity")],
)
def test_trust_does_not_replace_human_independence_and_identity_guards(
    case: _OperatorCase, reviewer: str, message: str
) -> None:
    payload = _approved(case)
    provenance = cast(dict[str, object], payload["provenance"])
    reviewer = cast(str, provenance["generated_by"]) if message == "independent human" else reviewer
    review = cast(dict[str, object], payload["review"])
    review["human_reviewer"] = reviewer
    review[case.digest_field] = _approval_digest(payload, field=case.digest_field)

    with pytest.raises(ValueError, match=message):
        case.validate(payload, case.contract(), frozenset({_trusted(case, payload)}))


@pytest.mark.parametrize("case", CASES)
def test_trusted_approval_cannot_escalate_runtime_authority(case: _OperatorCase) -> None:
    payload = _approved(case)
    trusted = _trusted(case, payload)
    authority_field = (
        "runtime_authorized"
        if case.kind is OperatorApprovalKind.D_MAPPING_PROPOSAL
        else "operator_g_eligible"
    )
    payload[authority_field] = True

    with pytest.raises(ValueError, match=authority_field):
        case.validate(payload, case.contract(), frozenset({trusted}))


@pytest.mark.parametrize(
    ("digest", "reviewer", "approved_at", "message"),
    [
        ("A" * 64, "human:reviewer", datetime.now(UTC), "lowercase SHA-256"),
        ("a" * 64, " human:reviewer", datetime.now(UTC), "nonblank exact identity"),
        ("a" * 64, "human:reviewer", datetime.now(timezone(timedelta(hours=1))), "UTC"),
    ],
)
def test_trusted_approval_rejects_noncanonical_tuple_values(
    digest: str, reviewer: str, approved_at: datetime, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        TrustedOperatorApproval(
            kind=OperatorApprovalKind.D_MAPPING_PROPOSAL,
            content_digest=digest,
            reviewer_identity=reviewer,
            approved_at_utc=approved_at,
        )


def test_submitted_d_approval_accepts_a_utc_datetime_instant() -> None:
    # Given: detached trust and submitted metadata sharing one UTC datetime
    digest = "a" * 64
    instant = datetime(2026, 9, 11, 12, tzinfo=UTC)
    review = {
        "human_reviewer": "human:d-reviewer",
        "human_approved_at_utc": instant,
        "approved_proposal_digest": digest,
    }
    trusted = TrustedOperatorApproval(
        OperatorApprovalKind.D_MAPPING_PROPOSAL,
        digest,
        "human:d-reviewer",
        instant,
    )

    # When/Then: the shared submitted boundary preserves datetime support
    require_operator_d_approval(
        review,
        generated_by="agent:d-producer",
        expected_digest=digest,
        trusted_approvals=frozenset({trusted}),
    )


@pytest.mark.parametrize(
    "instant",
    [
        "not-an-instant",
        42,
        datetime(2026, 9, 11, 12, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_submitted_d_approval_rejects_malformed_or_non_utc_instants(instant: object) -> None:
    # Given: otherwise complete D approval metadata with an invalid instant
    review = {
        "human_reviewer": "human:d-reviewer",
        "human_approved_at_utc": instant,
        "approved_proposal_digest": "a" * 64,
    }

    # When/Then: malformed, mistyped, and non-UTC values fail at the time boundary
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        require_operator_d_approval(
            review,
            generated_by="agent:d-producer",
            expected_digest="a" * 64,
            trusted_approvals=frozenset(),
        )


def test_operator_g_rejects_non_string_submitted_approval_instant() -> None:
    # Given: G approval metadata carrying a datetime instead of its required ISO string
    review = {"human_approved_at_utc": datetime(2026, 9, 11, 12, tzinfo=UTC)}

    # When/Then: G rejects before digest or trust lookup
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        require_operator_g_approval(
            review,
            generated_by="agent:g-producer",
            producer_session="session:g-producer",
            completed_at_utc=datetime(2026, 9, 11, 11, tzinfo=UTC),
            expected_digest="a" * 64,
            trusted_approvals=frozenset(),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("reviewer_session", " session:g-reviewer", "nonblank exact value"),
        ("approval_scope", "runtime_authority", "operator_g_record_admission"),
        ("approved_record_digest", None, "approved digest is required"),
    ],
)
def test_operator_g_rejects_malformed_submitted_binding_fields(
    field: str, value: object, message: str
) -> None:
    # Given: one malformed field in otherwise exact G submitted metadata
    review: dict[str, object] = {
        "human_reviewer": "human:g-reviewer",
        "human_approved_at_utc": "2026-09-11T12:00:00Z",
        "reviewer_session": "session:g-reviewer",
        "approval_scope": "operator_g_record_admission",
        "approved_record_digest": "a" * 64,
    }
    review[field] = value

    # When/Then: each malformed binding is rejected before detached trust lookup
    with pytest.raises(ValueError, match=message):
        require_operator_g_approval(
            review,
            generated_by="agent:g-producer",
            producer_session="session:g-producer",
            completed_at_utc=datetime(2026, 9, 11, 11, tzinfo=UTC),
            expected_digest="a" * 64,
            trusted_approvals=frozenset(),
        )


def test_trusted_approval_rejects_session_without_scope() -> None:
    # Given/When/Then: a partial detached session binding cannot be represented
    with pytest.raises(ValueError, match="supplied together"):
        TrustedOperatorApproval(
            OperatorApprovalKind.G_FAILURE_RECORD,
            "a" * 64,
            "human:g-reviewer",
            datetime(2026, 9, 11, 12, tzinfo=UTC),
            reviewer_session="session:g-reviewer",
        )
