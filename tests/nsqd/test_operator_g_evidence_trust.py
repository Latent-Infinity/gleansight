from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, assert_never

import pytest

from nsqd.domain.operator_g_census import (
    CensusStatus,
    ReasonCode,
)
from nsqd.domain.operator_g_evidence import (
    OperatorGEvidenceRole,
    TrustedEvidenceArtifactError,
    TrustedOperatorGEvidenceArtifact,
)
from nsqd.infrastructure.operator_g_census import CensusLimits, census_operator_g_evidence
from tests.nsqd.operator_g_census_support import (
    approved_record,
    census_contract,
    initialize_repository,
    trusted_approval,
    trusted_evidence_artifacts,
    write_evidence,
    write_record,
)

type EvidenceFailure = Literal["missing", "tampered", "symlink", "oversize", "out-of-scope"]


def test_present_evidence_bytes_without_role_trust_do_not_qualify(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    record = approved_record(write_evidence(tmp_path))
    write_record(tmp_path, record)

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
    )

    assert census.status is CensusStatus.INCOMPLETE
    assert census.candidates[0].reason_code is ReasonCode.MISSING_EVIDENCE
    assert census.candidates[0].qualifying is False


def test_wrong_or_partial_evidence_role_registry_does_not_qualify(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    digest = write_evidence(tmp_path)
    record = approved_record(digest)
    write_record(tmp_path, record)
    all_roles = tuple(OperatorGEvidenceRole)
    registries = (
        trusted_evidence_artifacts(digest, roles=all_roles[:2]),
        trusted_evidence_artifacts(
            digest, roles=(OperatorGEvidenceRole.IMMUTABLE_SOURCE_ARTIFACT,)
        ),
        trusted_evidence_artifacts(digest, path="docs/wrong.json"),
        trusted_evidence_artifacts("0" * 64),
    )

    for registry in registries:
        census = census_operator_g_evidence(
            tmp_path,
            contract=census_contract(),
            trusted_approvals=frozenset({trusted_approval(record)}),
            trusted_evidence_artifacts=registry,
        )
        assert census.status is CensusStatus.INCOMPLETE
        assert census.candidates[0].reason_code is ReasonCode.MISSING_EVIDENCE


def test_exact_role_complete_evidence_registry_qualifies(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    digest = write_evidence(tmp_path)
    record = approved_record(digest)
    write_record(tmp_path, record)

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(digest),
    )

    assert census.status is CensusStatus.COMPLETE
    assert census.candidates[0].qualifying is True
    assert census.trusted_approval_count == 1
    assert census.trusted_evidence_artifact_count == len(OperatorGEvidenceRole)


@pytest.mark.parametrize("suffix", [".bin", ".csv", ".log", ".pdf"])
def test_exact_trusted_unstructured_evidence_bytes_qualify(tmp_path: Path, suffix: str) -> None:
    # Given: approved structured metadata bound to exact trusted unstructured bytes
    initialize_repository(tmp_path)
    content = b"\x00\xfftrusted-evidence\n"
    evidence_path = f"docs/evidence{suffix}"
    (tmp_path / evidence_path).write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    record = approved_record(digest)
    write_record(tmp_path, record)

    # When: the census verifies evidence independently from structured discovery
    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(digest, path=evidence_path),
    )

    # Then: bytes qualify without becoming a discovered or parsed structured record
    assert census.status is CensusStatus.COMPLETE
    assert census.scope_file_count == 1
    assert census.candidates[0].qualifying is True


@pytest.mark.parametrize("failure", ["missing", "tampered", "symlink", "oversize", "out-of-scope"])
def test_unsafe_trusted_unstructured_evidence_fails_closed(
    tmp_path: Path, failure: EvidenceFailure
) -> None:
    # Given: a trusted registry entry whose exact bytes cannot be safely verified
    initialize_repository(tmp_path)
    trusted_content = b"trusted-binary-evidence"
    digest = hashlib.sha256(trusted_content).hexdigest()
    evidence_path = "docs/evidence.bin"
    match failure:
        case "missing":
            pass
        case "tampered":
            (tmp_path / evidence_path).write_bytes(b"tampered")
        case "symlink":
            outside = tmp_path / "outside-target.bin"
            outside.write_bytes(trusted_content)
            (tmp_path / evidence_path).symlink_to(outside)
        case "oversize":
            trusted_content = b"x" * 20_000
            digest = hashlib.sha256(trusted_content).hexdigest()
            (tmp_path / evidence_path).write_bytes(trusted_content)
        case "out-of-scope":
            evidence_path = "outside.bin"
            (tmp_path / evidence_path).write_bytes(trusted_content)
        case unreachable:
            assert_never(unreachable)
    record = approved_record(digest)
    write_record(tmp_path, record)

    # When: the census applies its existing scope and bounded-read policy
    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(digest, path=evidence_path),
        limits=CensusLimits(max_file_bytes=10_000),
    )

    # Then: no unsafe or mismatched path can satisfy evidence trust
    assert census.status is CensusStatus.INCOMPLETE
    assert census.candidates[0].reason_code is ReasonCode.MISSING_EVIDENCE
    assert census.candidates[0].qualifying is False


def test_submitted_trusted_evidence_metadata_is_not_promoted(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    digest = write_evidence(tmp_path)
    record = approved_record(digest)
    submitted = {
        "record": record,
        "trusted_evidence_artifacts": [
            {"role": role.value, "path": "docs/evidence.json", "sha256": digest}
            for role in OperatorGEvidenceRole
        ],
    }
    write_record(tmp_path, submitted)

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
    )

    assert census.status is CensusStatus.INCOMPLETE
    assert census.candidates[0].reason_code is ReasonCode.MISSING_EVIDENCE


def test_symlinked_trusted_evidence_does_not_qualify(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}\n")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (tmp_path / "docs" / "evidence.json").symlink_to(outside)
    record = approved_record(digest)
    write_record(tmp_path, record)

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(digest),
    )

    assert census.status is CensusStatus.INCOMPLETE
    assert census.candidates[0].reason_code is ReasonCode.MISSING_EVIDENCE


@pytest.mark.parametrize(
    ("path", "digest"),
    [("../outside.json", "0" * 64), (" docs/a.json", "0" * 64), ("docs/a.json", "A" * 64)],
)
def test_trusted_evidence_artifact_rejects_invalid_boundaries(path: str, digest: str) -> None:
    role = OperatorGEvidenceRole.IMMUTABLE_SOURCE_ARTIFACT

    with pytest.raises(TrustedEvidenceArtifactError):
        TrustedOperatorGEvidenceArtifact(role, path, digest)
