from __future__ import annotations

import json
from pathlib import Path

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.operator_g_census import CensusStatus, ReasonCode
from nsqd.domain.operator_g_readiness import project_zero_readiness
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from nsqd.infrastructure.operator_g_census_files import CensusScope
from tests.nsqd.operator_g_census_support import (
    APPROVED_INPUT_ROOT,
    approved_record,
    census_contract,
    initialize_repository,
    trusted_approval,
    trusted_evidence_artifacts,
    write_evidence,
    write_record,
)


def test_default_scope_truthfully_reports_empty_admitted_inventory(tmp_path: Path) -> None:
    # Given: the canonical admitted-evidence directory exists without approved records
    initialize_repository(tmp_path)

    # When: the default census scans its versioned evidence input
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    # Then: zero means no admitted records in that explicit scope
    assert census.status is CensusStatus.COMPLETE
    assert census.configuration.roots == (APPROVED_INPUT_ROOT,)
    assert census.scope_file_count == 0
    assert census.candidates == ()
    assert census.qualifying_record_digests == ()
    assert census.substantiates_zero is True


def test_zero_projection_declares_narrow_scope_without_granting_authority(tmp_path: Path) -> None:
    # Given: a complete empty census of the canonical admitted inventory
    initialize_repository(tmp_path)
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    # When: readiness is projected from that explicit scope
    projection = project_zero_readiness(census, ())

    # Then: scope is explicit while every report-only authority flag remains false
    projected_census = projection["census"]
    authority = projection["authority"]
    assert isinstance(projected_census, dict)
    assert isinstance(authority, dict)
    assert projected_census["input_scope"] == {
        "kind": "versioned_evidence_roots",
        "roots": [APPROVED_INPUT_ROOT],
    }
    assert projection["authorization_state"] == "report_only"
    assert all(value is False for value in authority.values())


def test_default_scope_is_unchanged_by_docs_archive_and_output_files(tmp_path: Path) -> None:
    # Given: an empty canonical scope and an initial census
    initialize_repository(tmp_path)
    initial = census_operator_g_evidence(tmp_path, contract=census_contract())

    # When: unrelated source, documentation, archive, and report files are added
    for relative in (
        "src/nsqd/new.json",
        "docs/new.json",
        "evidence/archive/reviews/v1/historical.json",
        "output/operator-g/readiness.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"failure_record_id":"outside-scope"}', encoding="utf-8")
    current = census_operator_g_evidence(tmp_path, contract=census_contract())

    # Then: positive input scope makes every unrelated addition irrelevant
    assert current.scope_snapshot_digest == initial.scope_snapshot_digest
    assert current.scope_file_count == 0
    assert current.candidates == ()


def test_record_placement_does_not_supply_approval_or_evidence_trust(tmp_path: Path) -> None:
    # Given: a nominally approved record and its evidence are placed under an admitted root
    initialize_repository(tmp_path)
    evidence_digest = write_evidence(tmp_path)
    write_record(tmp_path, approved_record(evidence_digest))

    # When: no caller-supplied trust registries are provided
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    # Then: placement alone cannot promote the record to trusted evidence
    assert census.status is CensusStatus.INCOMPLETE
    assert census.qualifying_record_digests == ()
    assert census.candidates[0].reason_code is ReasonCode.UNTRUSTED


def test_explicit_custom_scope_admits_only_exact_trusted_paths(tmp_path: Path) -> None:
    # Given: a complete record and evidence under a caller-declared input root
    input_root = "incoming/operator-g/v2"
    (tmp_path / input_root).mkdir(parents=True)
    evidence_digest = write_evidence(tmp_path, input_root=input_root)
    record = approved_record(evidence_digest)
    write_record(tmp_path, record, input_root=input_root)

    # When: both the scope and independent trust registries name those exact paths
    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        scope=CensusScope((input_root,)),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(
            evidence_digest,
            path=f"{input_root}/evidence.json",
        ),
    )

    # Then: the complete trusted record qualifies within the declared scope
    assert census.status is CensusStatus.COMPLETE
    assert len(census.qualifying_record_digests) == 1
    assert census.candidates[0].qualifying is True


def test_historical_354_scope_remains_an_immutable_replay_fixture() -> None:
    # Given: the historical report retains its original logical path identity
    repository_root = Path(__file__).resolve().parents[2]
    logical_path = Path(
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-schema-closure/readiness.json"
    )

    # When: the historical payload is read through the closed archive resolver
    payload = json.loads(
        resolve_artifact_path(repository_root, logical_path).read_text(encoding="utf-8")
    )
    census = payload["census"]

    # Then: its broad historical declaration is retained rather than reinterpreted
    assert census["repository_roots"] == ["docs", "src", "tests"]
    assert census["scope_file_count"] == 354
    assert census["scope_snapshot_digest"] == (
        "b930b81be31ebdad3e9007c6b96963939dc73915da6a896f8914ba9e3b2abbb4"
    )
