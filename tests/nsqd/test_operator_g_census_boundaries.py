from __future__ import annotations

from pathlib import Path

import pytest

from nsqd.domain.operator_g_census import CensusStatus
from nsqd.infrastructure import operator_g_census_files
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from nsqd.infrastructure.operator_g_census_files import (
    APPROVED_INPUT_ROOT,
    CensusLimits,
    CensusScope,
    InvalidCensusScopeError,
    SafeReadError,
)
from tests.nsqd.operator_g_census_support import census_contract, initialize_repository


def test_missing_declared_root_makes_census_incomplete(tmp_path: Path) -> None:
    # Given: a repository without the declared evidence root
    tmp_path.mkdir(exist_ok=True)

    # When: the census scans that explicit root
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    # Then: absence cannot be interpreted as a trustworthy zero inventory
    assert census.status is CensusStatus.INCOMPLETE
    assert census.substantiates_zero is False
    assert census.issues[0].reason == "missing_or_unsafe_scope_root"


@pytest.mark.parametrize("root", ["", ".", "/absolute", "../escape", "a/../b", "a/./b", "a\\b"])
def test_invalid_scope_roots_are_rejected_at_construction(root: str) -> None:
    # Given: a noncanonical or unsafe root
    # When/Then: the typed scope boundary rejects it before filesystem access
    with pytest.raises(InvalidCensusScopeError):
        CensusScope((root,))


def test_symlink_and_file_size_limit_make_census_incomplete(tmp_path: Path) -> None:
    # Given: a symlink and an oversized structured file in the admitted scope
    initialize_repository(tmp_path)
    input_root = tmp_path / APPROVED_INPUT_ROOT
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (input_root / "escape.json").symlink_to(outside)
    (input_root / "large.json").write_text("{}", encoding="utf-8")

    # When: bounded discovery reads the scope
    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        limits=CensusLimits(max_file_bytes=1),
    )

    # Then: both unsafe conditions are explicit and zero is not substantiated
    reasons = {issue.reason for issue in census.issues}
    assert reasons == {"file_size_limit_exceeded", "symlink_in_scope"}
    assert census.substantiates_zero is False


@pytest.mark.parametrize(
    ("limits", "relative_path", "reason"),
    [
        (CensusLimits(max_files=0), "a.json", "file_count_limit_exceeded"),
        (CensusLimits(max_total_bytes=1), "a.json", "total_size_limit_exceeded"),
        (CensusLimits(max_depth=6), "deep/a.json", "depth_limit_exceeded"),
        (
            CensusLimits(max_structured_depth=1),
            "a.json",
            "canonical_record_validation_failed",
        ),
    ],
)
def test_each_scan_limit_is_explicit(
    tmp_path: Path, limits: CensusLimits, relative_path: str, reason: str
) -> None:
    # Given: nested candidate data under the canonical root
    initialize_repository(tmp_path)
    path = tmp_path / APPROVED_INPUT_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"a":{"b":{"failure_record_id":"x"}}}', encoding="utf-8")

    # When: a single scan limit is reached
    census = census_operator_g_evidence(tmp_path, contract=census_contract(), limits=limits)

    # Then: the scan is incomplete for that exact reason
    assert census.status is CensusStatus.INCOMPLETE
    assert reason in {issue.reason for issue in census.issues}


def test_failed_no_follow_read_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: an admitted file whose race-safe read fails
    initialize_repository(tmp_path)
    relative = f"{APPROVED_INPUT_ROOT}/unreadable.json"
    (tmp_path / relative).write_text("{}", encoding="utf-8")
    original = operator_g_census_files._read_nofollow

    def fail_selected(root: Path, candidate: str, max_bytes: int) -> bytes:
        if candidate == relative:
            raise SafeReadError("unsafe_nofollow_read")
        return original(root, candidate, max_bytes)

    monkeypatch.setattr(operator_g_census_files, "_read_nofollow", fail_selected)

    # When: the census reads the declared scope
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    # Then: the read failure prevents a complete zero result
    assert "unsafe_nofollow_read" in {issue.reason for issue in census.issues}


@pytest.mark.parametrize(
    "payload",
    [
        "value: !!binary SGVsbG8=\n",
        "value: !!set {one: null}\n",
        "!!omap\n- one: 1\n- two: 2\n",
        "!!pairs\n- one: 1\n- two: 2\n",
    ],
)
def test_unsupported_yaml_value_makes_census_incomplete(tmp_path: Path, payload: str) -> None:
    # Given: a structured value outside the normalized evidence union
    initialize_repository(tmp_path)
    (tmp_path / APPROVED_INPUT_ROOT / "unsupported.yaml").write_text(payload, encoding="utf-8")

    # When: census discovery parses the admitted file
    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    # Then: malformed evidence fails closed
    assert census.status is CensusStatus.INCOMPLETE
    assert "malformed_structured_file" in {issue.reason for issue in census.issues}


def test_reverse_creation_order_has_same_snapshot(tmp_path: Path) -> None:
    # Given: equal admitted inventories created in opposite order
    first = tmp_path / "first"
    second = tmp_path / "second"
    initialize_repository(first)
    initialize_repository(second)
    for root, names in ((first, ("a.json", "b.yaml")), (second, ("b.yaml", "a.json"))):
        for name in names:
            (root / APPROVED_INPUT_ROOT / name).write_text("{}\n", encoding="utf-8")

    # When: both repositories are censused
    first_census = census_operator_g_evidence(first, contract=census_contract())
    second_census = census_operator_g_evidence(second, contract=census_contract())

    # Then: filesystem creation order does not affect the inventory digest
    assert first_census.scope_snapshot_digest == second_census.scope_snapshot_digest
