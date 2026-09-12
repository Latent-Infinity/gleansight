from __future__ import annotations

import json
from pathlib import Path

import pytest

from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    operator_g_registration_digest,
)
from nsqd.domain.operator_g_census import CandidateClass, CensusStatus, ReasonCode
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from tests.nsqd.operator_g_census_support import (
    approved_record,
    census_contract,
    initialize_repository,
    mapping,
    trusted_approval,
    trusted_evidence_artifacts,
    write_evidence,
    write_record,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_real_repository_census_replays_exact_inventory() -> None:
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())

    assert census.status is CensusStatus.COMPLETE
    assert census.scope_file_count == 354
    assert (
        census.scope_snapshot_digest
        == "b930b81be31ebdad3e9007c6b96963939dc73915da6a896f8914ba9e3b2abbb4"
    )
    assert census.trusted_approval_count == 0
    assert census.trusted_evidence_artifact_count == 0
    assert census.qualifying_record_digests == ()
    observed = {item.candidate_class: item.observed_count for item in census.inventory}
    assert observed == {
        CandidateClass.JOB_ERROR: 0,
        CandidateClass.SUFFICIENCY_FAILURE: 0,
        CandidateClass.SYNTHETIC_FIXTURE: 1,
        CandidateClass.TAU_MEASUREMENT: 120,
        CandidateClass.TEST_FAILURE: 0,
        CandidateClass.UNEXECUTED_STUDY: 120,
    }


def test_independently_trusted_complete_record_qualifies(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    evidence_digest = write_evidence(tmp_path)
    record = approved_record(evidence_digest)
    write_record(tmp_path, record)

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(evidence_digest),
    )

    assert census.status is CensusStatus.COMPLETE
    assert len(census.qualifying_record_digests) == 1
    assert census.candidates[0].qualifying is True


def test_incomplete_scan_cannot_retain_a_qualifying_record_digest(tmp_path: Path) -> None:
    # Given: a trusted complete record beside malformed in-scope bytes
    initialize_repository(tmp_path)
    evidence_digest = write_evidence(tmp_path)
    record = approved_record(evidence_digest)
    write_record(tmp_path, record)
    (tmp_path / "docs" / "malformed.json").write_bytes(b"\xff\xfe")

    # When: the repository evidence census scans the incomplete scope
    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(evidence_digest),
    )

    # Then: incomplete evidence cannot preserve an admission-bearing digest
    assert census.status is CensusStatus.INCOMPLETE
    assert census.qualifying_record_digests == ()


@pytest.mark.parametrize(
    ("trust", "remove_evidence", "reason"),
    [
        (False, False, ReasonCode.UNTRUSTED),
        (True, True, ReasonCode.MISSING_EVIDENCE),
    ],
)
def test_untrusted_or_missing_evidence_cannot_substantiate_zero(
    tmp_path: Path,
    trust: bool,
    remove_evidence: bool,
    reason: ReasonCode,
) -> None:
    initialize_repository(tmp_path)
    evidence_digest = write_evidence(tmp_path)
    record = approved_record(evidence_digest)
    write_record(tmp_path, record)
    if remove_evidence:
        (tmp_path / "docs" / "evidence.json").unlink()
    approvals = frozenset({trusted_approval(record)}) if trust else frozenset()
    evidence_trust = trusted_evidence_artifacts(evidence_digest) if trust else frozenset()

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=approvals,
        trusted_evidence_artifacts=evidence_trust,
    )

    assert census.status is CensusStatus.INCOMPLETE
    assert census.substantiates_zero is False
    assert census.candidates[0].reason_code is reason


def test_forged_submitted_approval_is_not_promoted_to_trust(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    record = approved_record(write_evidence(tmp_path))
    review = mapping(record["review"])
    submitted = {
        "record": record,
        "trusted_approvals": [
            {
                "kind": "operator_g_failure_record",
                "content_digest": review["approved_record_digest"],
                "reviewer_identity": review["human_reviewer"],
                "approved_at_utc": review["human_approved_at_utc"],
            }
        ],
    }
    write_record(tmp_path, submitted)

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert census.qualifying_record_digests == ()
    assert census.candidates[0].reason_code is ReasonCode.UNTRUSTED


def test_forbidden_and_malformed_candidates_fail_closed(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    forbidden = approved_record(write_evidence(tmp_path))
    forbidden["source_class"] = "job_error_code"
    write_record(tmp_path, forbidden, "forbidden.json")
    (tmp_path / "docs" / "malformed.json").write_text('{"failure_record_id":', encoding="utf-8")

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert census.status is CensusStatus.INCOMPLETE
    assert {item.reason_code for item in census.candidates} == {
        ReasonCode.FORBIDDEN_SOURCE,
        ReasonCode.MALFORMED,
    }


@pytest.mark.parametrize(
    "source_class",
    [
        "test_failure_without_experiment_evidence",
        "job_error_code",
        "sufficiency_failure",
        "inferred_or_invented_failure",
        "absence_of_published_or_successful_results",
    ],
)
def test_every_forbidden_record_class_is_nonqualifying(tmp_path: Path, source_class: str) -> None:
    initialize_repository(tmp_path)
    record = approved_record(write_evidence(tmp_path))
    record["source_class"] = source_class
    write_record(tmp_path, record)

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert census.qualifying_record_digests == ()
    assert census.candidates[0].reason_code is ReasonCode.FORBIDDEN_SOURCE


def test_supported_formats_and_nested_locators_are_sorted(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    payload = {"outer": [{"failure_record_id": "pending"}]}
    (tmp_path / "docs" / "d.yaml").write_text("outer:\n  - failure_record_id: pending\n")
    (tmp_path / "docs" / "c.yml").write_text("outer:\n  - failure_record_id: pending\n")
    (tmp_path / "docs" / "b.jsonl").write_text(json.dumps(payload) + "\n")
    (tmp_path / "docs" / "a.json").write_text(json.dumps(payload))
    (tmp_path / "docs" / "e.toml").write_text('failure_record_id = "pending"\n')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    locators = tuple(str(item.locator) for item in census.candidates)
    assert locators == tuple(sorted(locators))
    assert len(locators) == 5
    assert all(item.reason_code is ReasonCode.MALFORMED for item in census.candidates)


def test_duplicate_digest_deduplicates_and_conflicting_id_rejects(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    evidence_digest = write_evidence(tmp_path)
    record = approved_record(evidence_digest)
    write_record(tmp_path, record, "a.json")
    write_record(tmp_path, record, "b.json")
    approvals = frozenset({trusted_approval(record)})

    duplicate = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=approvals,
        trusted_evidence_artifacts=trusted_evidence_artifacts(evidence_digest),
    )
    assert len(duplicate.qualifying_record_digests) == 1
    assert sum(item.qualifying for item in duplicate.candidates) == 1

    changed = mapping(record)
    changed["experiment_id"] = "different"
    changed_record = approved_record(write_evidence(tmp_path))
    changed_record["experiment_id"] = "different"
    changed_record["registration_digest"] = operator_g_registration_digest(changed_record)
    review = mapping(changed_record["review"])
    review["approved_record_digest"] = None
    changed_record["review"] = review
    review["approved_record_digest"] = operator_g_failure_record_digest(changed_record)
    changed_record["review"] = review
    write_record(tmp_path, changed_record, "b.json")
    approvals = frozenset({trusted_approval(record), trusted_approval(changed_record)})

    conflict = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=approvals,
        trusted_evidence_artifacts=trusted_evidence_artifacts(evidence_digest),
    )
    assert conflict.status is CensusStatus.INCOMPLETE
    assert all(item.reason_code is ReasonCode.CONFLICTING_ID for item in conflict.candidates)
