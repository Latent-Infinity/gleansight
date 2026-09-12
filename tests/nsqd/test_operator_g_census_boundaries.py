from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nsqd.domain.operator_g_census import CandidateClass, CensusStatus
from nsqd.infrastructure import operator_g_census_files
from nsqd.infrastructure.operator_g_census import CensusLimits, census_operator_g_evidence
from nsqd.infrastructure.operator_g_census_files import SafeReadError
from nsqd.infrastructure.operator_g_census_formats import (
    StructuredFormatError,
    normalize,
    parse_documents,
)
from tests.nsqd.operator_g_census_support import census_contract, initialize_repository


def test_only_exact_readiness_output_directories_are_excluded(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    exact = tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-schema-closure"
    similar = tmp_path / "docs/reviews/product-readiness-notes"
    exact.mkdir(parents=True)
    similar.mkdir(parents=True)
    (exact / "record.json").write_text('{"failure_record_id":"excluded"}')
    (similar / "record.json").write_text('{"failure_record_id":"included"}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert len(census.candidates) == 1
    assert str(census.candidates[0].locator).startswith("docs/reviews/product-readiness-notes/")


def test_protocol_and_ordinary_files_are_scanned_while_census_self_output_is_excluded(
    tmp_path: Path,
) -> None:
    initialize_repository(tmp_path)
    protocol = tmp_path / "docs/reviews/nsqd-operator-evidence-resolution-2026-09-09"
    census_output = (
        tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-schema-closure"
    )
    ordinary = tmp_path / "docs/reviews/operator-evidence-notes"
    protocol.mkdir(parents=True)
    census_output.mkdir(parents=True)
    ordinary.mkdir(parents=True)
    (protocol / "protocol.json").write_text('{"failure_record_id":"protocol"}')
    (census_output / "readiness.json").write_text('{"failure_record_id":"excluded"}')
    (ordinary / "record.json").write_text('{"failure_record_id":"included"}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    locators = {str(candidate.locator) for candidate in census.candidates}
    assert len(census.candidates) == 2
    assert any(locator.startswith("docs/reviews/operator-evidence-notes/") for locator in locators)
    assert any(
        locator.startswith("docs/reviews/nsqd-operator-evidence-resolution-2026-09-09/")
        for locator in locators
    )


def test_historical_c_cycle_census_output_is_scanned(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    exact = tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle"
    similar = tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle-notes"
    exact.mkdir(parents=True)
    similar.mkdir(parents=True)
    (exact / "readiness.json").write_text('{"failure_record_id":"excluded"}')
    (similar / "record.json").write_text('{"failure_record_id":"included"}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    locators = {str(candidate.locator) for candidate in census.candidates}
    assert len(locators) == 2
    assert any("2026-09-09-c-cycle/readiness.json" in locator for locator in locators)
    assert any("2026-09-09-c-cycle-notes/record.json" in locator for locator in locators)


def test_historical_c_cycle_correction_output_is_scanned(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    exact = tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle-correction"
    similar = (
        tmp_path
        / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-cycle-correction-notes"
    )
    exact.mkdir(parents=True)
    similar.mkdir(parents=True)
    (exact / "readiness.json").write_text('{"failure_record_id":"excluded"}')
    (similar / "record.json").write_text('{"failure_record_id":"included"}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    locators = {str(candidate.locator) for candidate in census.candidates}
    assert len(locators) == 2
    assert any("c-cycle-correction/readiness.json" in locator for locator in locators)
    assert any("c-cycle-correction-notes/record.json" in locator for locator in locators)


def test_historical_c_review_output_tree_is_scanned(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    exact = tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review"
    similar = tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review-notes"
    exact.mkdir(parents=True)
    (exact / "nested").mkdir()
    similar.mkdir(parents=True)
    (exact / "readiness.json").write_text('{"failure_record_id":"excluded"}')
    (exact / "nested/record.json").write_text('{"failure_record_id":"excluded-descendant"}')
    (similar / "record.json").write_text('{"failure_record_id":"included"}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    locators = {str(candidate.locator) for candidate in census.candidates}
    assert len(locators) == 3
    assert any("c-review/readiness.json" in locator for locator in locators)
    assert any("c-review/nested/record.json" in locator for locator in locators)
    assert any("c-review-notes/record.json" in locator for locator in locators)


def test_historical_c_review_correction_output_tree_is_scanned(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    exact = (
        tmp_path / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review-correction"
    )
    similar = (
        tmp_path
        / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review-correction-notes"
    )
    exact.mkdir(parents=True)
    (exact / "nested").mkdir()
    similar.mkdir(parents=True)
    (exact / "readiness.json").write_text('{"failure_record_id":"excluded"}')
    (exact / "nested/record.json").write_text('{"failure_record_id":"excluded-descendant"}')
    (similar / "record.json").write_text('{"failure_record_id":"included"}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    locators = {str(candidate.locator) for candidate in census.candidates}
    assert len(locators) == 3
    assert any("c-review-correction/readiness.json" in locator for locator in locators)
    assert any("c-review-correction/nested/record.json" in locator for locator in locators)
    assert any("c-review-correction-notes/record.json" in locator for locator in locators)


def test_symlink_and_limits_make_census_incomplete(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    target = tmp_path / "outside.json"
    target.write_text("{}")
    (tmp_path / "docs" / "escape.json").symlink_to(target)
    (tmp_path / "docs" / "large.json").write_text("{}")

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        limits=CensusLimits(max_files=1, max_file_bytes=1, max_total_bytes=1, max_depth=1),
    )

    reasons = {issue.reason for issue in census.issues}
    assert "symlink_in_scope" in reasons
    assert "file_size_limit_exceeded" in reasons


@pytest.mark.parametrize(
    ("limits", "relative_path", "reason"),
    [
        (CensusLimits(max_files=0), "docs/a.json", "file_count_limit_exceeded"),
        (CensusLimits(max_total_bytes=1), "docs/a.json", "total_size_limit_exceeded"),
        (CensusLimits(max_depth=1), "docs/deep/a.json", "depth_limit_exceeded"),
        (CensusLimits(max_structured_depth=1), "docs/a.json", "canonical_record_validation_failed"),
    ],
)
def test_each_scan_limit_is_explicit(
    tmp_path: Path, limits: CensusLimits, relative_path: str, reason: str
) -> None:
    initialize_repository(tmp_path)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"a":{"b":{"failure_record_id":"x"}}}')

    census = census_operator_g_evidence(tmp_path, contract=census_contract(), limits=limits)

    assert census.status is CensusStatus.INCOMPLETE
    assert reason in {issue.reason for issue in census.issues}


def test_failed_no_follow_read_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_repository(tmp_path)
    (tmp_path / "docs" / "unreadable.json").write_text("{}")
    original = operator_g_census_files._read_nofollow

    def fail_selected(root: Path, relative: str, max_bytes: int) -> bytes:
        if relative == "docs/unreadable.json":
            raise SafeReadError("unsafe_nofollow_read")
        return original(root, relative, max_bytes)

    monkeypatch.setattr(operator_g_census_files, "_read_nofollow", fail_selected)

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert "unsafe_nofollow_read" in {issue.reason for issue in census.issues}


def _write_calibration(root: Path, count: int) -> None:
    pairs = [(f"hash-{index}", f"digest-{index}") for index in range(count)]
    measurements = "".join(
        json.dumps({"candidate_artifact_hash": candidate, "measurement_artifact_digest": digest})
        + "\n"
        for candidate, digest in pairs
    )
    candidates = json.dumps(
        {"candidates": [{"id": f"candidate-{index}"} for index in range(count)]},
        sort_keys=True,
    )
    hashes = {
        "candidate_packet_sha256": hashlib.sha256(candidates.encode()).hexdigest(),
        "policy": [
            {
                "candidate_id": f"candidate-{index}",
                "candidate_artifact_hash": candidate,
                "measurement_artifact_digest": digest,
            }
            for index, (candidate, digest) in enumerate(pairs)
        ],
    }
    root.mkdir(parents=True)
    (root / "measurements.jsonl").write_text(measurements)
    (root / "candidates.json").write_text(candidates)
    (root / "candidate-hashes.json").write_text(json.dumps(hashes))


def test_multiple_calibration_roots_are_aggregated(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    reviews = tmp_path / "docs/reviews"
    _write_calibration(reviews / "nsqd-tau-calibration-one", 2)
    _write_calibration(reviews / "nsqd-tau-calibration-two", 3)

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    observed = {item.candidate_class: item.observed_count for item in census.inventory}
    assert census.status is CensusStatus.COMPLETE
    assert observed[CandidateClass.TAU_MEASUREMENT] == 5
    assert observed[CandidateClass.UNEXECUTED_STUDY] == 5


def test_yaml_and_toml_temporal_values_normalize_deterministically() -> None:
    yaml_document = parse_documents("value.yaml", b"created: 2026-09-08\n")
    toml_document = parse_documents("value.toml", b"created = 2026-09-08T01:02:03Z\n")

    assert yaml_document == [{"created": "2026-09-08"}]
    assert toml_document == [{"created": "2026-09-08T01:02:03+00:00"}]


@pytest.mark.parametrize(
    "payload",
    [
        "value: !!binary SGVsbG8=\n",
        "value: !!set {one: null}\n",
        "outer:\n  value: !!binary SGVsbG8=\n",
        "!!omap\n- one: 1\n- two: 2\n",
        "!!pairs\n- one: 1\n- two: 2\n",
        "outer: !!omap\n  - one: 1\n  - two: 2\n",
        "outer: !!pairs\n  - one: 1\n  - two: 2\n",
    ],
)
def test_unsupported_yaml_value_is_typed_and_makes_census_incomplete(
    tmp_path: Path, payload: str
) -> None:
    initialize_repository(tmp_path)
    (tmp_path / "docs" / "unsupported.yaml").write_text(payload)

    with pytest.raises(StructuredFormatError):
        parse_documents("unsupported.yaml", payload.encode())
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert census.status is CensusStatus.INCOMPLETE
    assert census.substantiates_zero is False
    assert "malformed_structured_file" in {issue.reason for issue in census.issues}


def test_malformed_utf8_candidate_bytes_make_census_incomplete(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    (tmp_path / "docs" / "record.json").write_bytes(b"\xff\xfe")

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert census.status is CensusStatus.INCOMPLETE
    assert "malformed_structured_file" in {issue.reason for issue in census.issues}


def test_direct_tuple_value_is_typed_at_normalization_boundary() -> None:
    with pytest.raises(StructuredFormatError):
        normalize(("one", 1))


def test_reverse_creation_order_has_same_snapshot(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    initialize_repository(first)
    initialize_repository(second)
    for root, names in ((first, ("a.json", "b.yaml")), (second, ("b.yaml", "a.json"))):
        for name in names:
            (root / "docs" / name).write_text("{}\n")

    first_census = census_operator_g_evidence(first, contract=census_contract())
    second_census = census_operator_g_evidence(second, contract=census_contract())

    assert first_census.scope_snapshot_digest == second_census.scope_snapshot_digest
