from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

from nsqd.domain.operator_f import (
    operator_f_axis_proposal_digest,
    validate_operator_f_axis_contract,
    validate_operator_f_axis_proposal,
)

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reviews"
    / "nsqd-operator-activation-2026-08-30"
    / "axis-candidate-contract.yaml"
)


def _contract() -> dict[str, object]:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _proposal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "proposal_id": "F-PROP-001",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "schema_mutation_authorized": False,
        "domain_policy_id": "finance/1",
        "source_snapshot_ids": ["a" * 64],
        "existing_axis_inventory": ["mechanism", "target", "horizon"],
        "candidate_axis": {
            "name": "market_regime",
            "descriptor_kind": "novel_proposed",
            "semantic_definition": "Observable market stress regime at prediction time.",
            "measurement_protocol": "Classify from trailing volatility without future data.",
            "observation_window": "trailing_20_sessions",
            "value_type": "categorical",
            "domain": ["calm", "stress"],
            "known_confounds": ["volatility estimator choice"],
            "leakage_risks": ["future returns"],
        },
        "baselines": ["current_registered_axes"],
        "negative_controls": ["shuffled_candidate_axis"],
        "metrics": ["held_out_archive_coverage_gain"],
        "provenance": {
            "generated_by": "agent:f-proposer",
            "source_artifact_digests": ["b" * 64],
        },
        "review": {
            "status": "pending",
            "human_reviewer": None,
            "human_approved_at_utc": None,
            "approval_scope": None,
            "approved_proposal_digest": None,
        },
    }


def test_committed_operator_f_axis_contract_is_fail_closed() -> None:
    validated = validate_operator_f_axis_contract(_contract())
    assert validated["record_type"] == "operator_f_axis_proposal"
    assert validated["template_only"] is True
    assert validated["runtime_authorized"] is False
    assert validated["schema_mutation_authorized"] is False


def test_operator_f_axis_proposal_is_digest_bound_and_non_authorizing() -> None:
    validated = validate_operator_f_axis_proposal(_proposal(), contract=_contract())
    assert validated["candidate_axis"]["name"] == "market_regime"
    assert validated["runtime_authorized"] is False
    assert len(operator_f_axis_proposal_digest(validated)) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("runtime_authorized", True, "runtime_authorized"),
        ("schema_mutation_authorized", True, "schema_mutation_authorized"),
        ("candidate_axis", [], "candidate_axis"),
        ("baselines", [], "baselines"),
        ("negative_controls", [], "negative_controls"),
        ("metrics", [], "metrics"),
    ],
)
def test_operator_f_axis_proposal_rejects_unsafe_or_incomplete_rows(
    field: str,
    value: object,
    message: str,
) -> None:
    proposal = _proposal()
    proposal[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_f_axis_proposal(proposal, contract=_contract())


def test_operator_f_axis_proposal_rejects_duplicate_axes_and_self_approval() -> None:
    duplicate = _proposal()
    candidate_axis = cast(dict[str, object], copy.deepcopy(duplicate["candidate_axis"]))
    candidate_axis["name"] = "mechanism"
    duplicate["candidate_axis"] = candidate_axis
    with pytest.raises(ValueError, match="already registered"):
        validate_operator_f_axis_proposal(duplicate, contract=_contract())

    self_approved = _proposal()
    self_approved["review"] = {
        "status": "human_approved",
        "human_reviewer": "agent:f-proposer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approval_scope": "evaluation_only",
        "approved_proposal_digest": None,
    }
    with pytest.raises(ValueError, match="independent human"):
        validate_operator_f_axis_proposal(self_approved, contract=_contract())

    agent_approved = _proposal()
    agent_approved["review"] = {
        "status": "human_approved",
        "human_reviewer": "agent:independent-reviewer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approval_scope": "evaluation_only",
        "approved_proposal_digest": None,
    }
    with pytest.raises(ValueError, match="human reviewer"):
        validate_operator_f_axis_proposal(agent_approved, contract=_contract())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema_version"),
        ("record_type", "other", "record_type"),
        ("template_only", False, "template_only"),
        ("runtime_authorized", True, "runtime_authorized"),
        ("schema_mutation_authorized", True, "schema_mutation_authorized"),
        ("maximum_candidate_axes_per_proposal", 2, "exactly one"),
    ],
)
def test_operator_f_axis_contract_rejects_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    contract = _contract()
    contract[field] = value
    with pytest.raises(ValueError, match=message):
        validate_operator_f_axis_contract(contract)


def test_operator_f_axis_contract_and_proposal_reject_extra_fields() -> None:
    contract = _contract()
    contract["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_operator_f_axis_contract(contract)

    proposal = _proposal()
    provenance = cast(dict[str, object], proposal["provenance"])
    provenance["unexpected"] = True
    with pytest.raises(ValueError, match="provenance fields"):
        validate_operator_f_axis_proposal(proposal, contract=_contract())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"authorization_state": "authorized"}, "authorization_state"),
        ({"source_snapshot_ids": ["BAD"]}, "sha256"),
        ({"baselines": ["unregistered_baseline"]}, "contract-required"),
        ({"review": {"status": "agent_approved"}}, "fields do not match"),
    ],
)
def test_operator_f_axis_proposal_rejects_contract_drift(
    mutation: dict[str, object],
    message: str,
) -> None:
    proposal = _proposal()
    proposal.update(mutation)
    with pytest.raises(ValueError, match=message):
        validate_operator_f_axis_proposal(proposal, contract=_contract())


def test_operator_f_axis_proposal_validates_axis_enums_and_human_review() -> None:
    invalid_kind = _proposal()
    axis = cast(dict[str, object], copy.deepcopy(invalid_kind["candidate_axis"]))
    axis["descriptor_kind"] = "mystery"
    invalid_kind["candidate_axis"] = axis
    with pytest.raises(ValueError, match="descriptor_kind"):
        validate_operator_f_axis_proposal(invalid_kind, contract=_contract())

    invalid_value = _proposal()
    axis = cast(dict[str, object], copy.deepcopy(invalid_value["candidate_axis"]))
    axis["value_type"] = "opaque"
    invalid_value["candidate_axis"] = axis
    with pytest.raises(ValueError, match="value_type"):
        validate_operator_f_axis_proposal(invalid_value, contract=_contract())

    approved = _proposal()
    approved["review"] = {
        "status": "human_approved",
        "human_reviewer": "human:axis-reviewer",
        "human_approved_at_utc": "2026-09-05T20:00:00Z",
        "approval_scope": "evaluation_only",
        "approved_proposal_digest": None,
    }
    review = cast(dict[str, object], approved["review"])
    review["approved_proposal_digest"] = operator_f_axis_proposal_digest(approved)
    assert (
        validate_operator_f_axis_proposal(approved, contract=_contract())["review"]
        == approved["review"]
    )

    for field, value, message in (
        ("human_approved_at_utc", "not-a-date", "timezone-aware UTC"),
        ("approval_scope", "runtime", "approval_scope"),
    ):
        invalid = copy.deepcopy(approved)
        review = cast(dict[str, object], invalid["review"])
        review[field] = value
        with pytest.raises(ValueError, match=message):
            validate_operator_f_axis_proposal(invalid, contract=_contract())

    mutated = copy.deepcopy(approved)
    axis = cast(dict[str, object], mutated["candidate_axis"])
    axis["semantic_definition"] = "Mutated after approval."
    with pytest.raises(ValueError, match="approved_proposal_digest"):
        validate_operator_f_axis_proposal(mutated, contract=_contract())


def test_operator_f_axis_proposal_rejects_malformed_shapes_and_strings() -> None:
    with pytest.raises(ValueError, match="string-keyed mapping"):
        validate_operator_f_axis_proposal(
            cast(Mapping[str, object], "not-a-mapping"),
            contract=_contract(),
        )
    extra = _proposal()
    extra["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_operator_f_axis_proposal(extra, contract=_contract())
    blank = _proposal()
    blank["proposal_id"] = " "
    with pytest.raises(ValueError, match="proposal_id"):
        validate_operator_f_axis_proposal(blank, contract=_contract())
    duplicate = _proposal()
    duplicate["metrics"] = ["held_out_archive_coverage_gain"] * 2
    with pytest.raises(ValueError, match="unique"):
        validate_operator_f_axis_proposal(duplicate, contract=_contract())
