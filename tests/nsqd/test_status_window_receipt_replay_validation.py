from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from nsqd.domain.status_window_replay import (
    compare_status_window_semantics,
    derive_boundary_sensitivity_as_of,
    status_window_replay_artifact_digest,
    validate_status_window_replay_artifact,
)
from tests.nsqd.status_window_receipt_replay_support import (
    SEALED_AT_UTC,
    _artifact,
    _records,
)


def test_status_window_replay_artifact_rejects_tampering_and_policy_leakage() -> None:
    current_as_of = datetime(2026, 9, 2, 6, 45, tzinfo=UTC)
    boundary_as_of = datetime(2028, 9, 2, 6, 45, tzinfo=UTC)
    report = _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)

    tampered = {**report, "artifact_digest": "0" * 64}
    with pytest.raises(ValueError, match="artifact_digest"):
        validate_status_window_replay_artifact(tampered)

    tampered = cast(
        dict[str, Any], _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)
    )
    cast(dict[str, Any], tampered["source_receipt"])["record_count"] = 10
    with pytest.raises(ValueError, match="source_receipt"):
        validate_status_window_replay_artifact(tampered)

    tampered = cast(
        dict[str, Any], _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)
    )
    scenarios = cast(list[dict[str, Any]], tampered["scenarios"])
    cast(dict[str, Any], cast(dict[str, Any], scenarios[1]["policy_results"])["finance/1"])[
        "domain_policy_id"
    ] = "optimization/1"
    with pytest.raises(ValueError, match=r"policy_results\[finance/1\]"):
        validate_status_window_replay_artifact(tampered)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("schema_version", 2, "schema_version"),
        ("packet_kind", "wrong", "packet_kind"),
        ("authorization_state", "runtime", "authorization_state"),
        ("runtime_authorized", True, "runtime_authorized"),
        ("evidence_sufficient", False, "evidence_sufficient"),
        ("evidence_sufficient_scope", "runtime", "human_decision_only"),
        ("runtime_status_window_days", 731, "730 days"),
        ("sealed_at_utc", "2026-09-03T05:32:09Z", "sealed_at_utc"),
        ("harvested_at_provenance_caveat", "wrong", "provenance caveat"),
        ("extracted_records", "wrong", "extracted_records"),
        ("source_receipt", "wrong", "source_receipt"),
    ],
)
def test_status_window_replay_artifact_rejects_invalid_top_level_fields(
    field: str,
    value: object,
    match: str,
) -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    report[field] = value
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match=match):
        validate_status_window_replay_artifact(report)


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda report: cast(dict[str, Any], report).pop("sealed_at_utc"),
            "sealed_at_utc",
        ),
        (
            lambda report: cast(dict[str, Any], report).__setitem__(
                "generated_at_utc", SEALED_AT_UTC
            ),
            "generated_at_utc",
        ),
    ],
)
def test_status_window_replay_artifact_rejects_malformed_sealed_metadata(
    mutator: Any,
    match: str,
) -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    mutator(report)
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match=match):
        validate_status_window_replay_artifact(report)


def test_status_window_replay_artifact_rejects_invalid_scenario_shape() -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    report["scenarios"] = [{"scenario_id": "current_as_of"}]
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="scenarios"):
        validate_status_window_replay_artifact(report)

    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    scenarios = cast(list[dict[str, Any]], report["scenarios"])
    scenarios[0]["scenario_kind"] = "wrong"
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="scenario_kind"):
        validate_status_window_replay_artifact(report)

    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    scenarios = cast(list[dict[str, Any]], report["scenarios"])
    scenarios[0]["as_of_utc"] = "2026-09-02T06:45:01+00:00"
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="as_of_utc"):
        validate_status_window_replay_artifact(report)


def test_compare_requires_utc_and_boundary_derivation_handles_leap_day() -> None:
    with pytest.raises(ValueError, match="UTC"):
        compare_status_window_semantics(
            _records(),
            domain_policy_id="finance/1",
            as_of=datetime(2026, 9, 2, 6, 45),
            snapshot_state="production_valid",
        )

    leap_day_records = [dict(row) for row in _records()]
    for row in leap_day_records:
        row["harvested_at"] = "2024-02-29T06:45:00+00:00"
    with pytest.raises(ValueError, match="could not derive"):
        derive_boundary_sensitivity_as_of(leap_day_records)


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).append(
                dict(cast(list[dict[str, Any]], report["extracted_records"])[0])
            ),
            "exactly 11",
        ),
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).__setitem__(
                0,
                {
                    **cast(list[dict[str, Any]], report["extracted_records"])[0],
                    "record_id": "synthetic-record-0",
                },
            ),
            "extracted_records_digest",
        ),
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).__setitem__(
                0,
                cast(list[dict[str, Any]], report["extracted_records"])[1],
            ),
            "record ids must be unique",
        ),
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).__setitem__(
                0,
                {
                    **cast(list[dict[str, Any]], report["extracted_records"])[0],
                    "domain_policy_id": "optimization/1",
                },
            ),
            "6 finance and 5 optimization",
        ),
    ],
)
def test_validation_rejects_invalid_extracted_records(
    mutator: Any,
    match: str,
) -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    mutator(report)
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match=match):
        validate_status_window_replay_artifact(report)

    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    records = cast(list[dict[str, Any]], report["extracted_records"])
    records[0]["harvested_at"] = "2026-09-02T06:45:00"
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="harvested_at rows"):
        validate_status_window_replay_artifact(report)
