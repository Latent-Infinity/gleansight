from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from nsqd.domain.ablation import (
    CALENDAR_WINDOW_MONTHS,
    calendar_month_cutoff,
    calendar_month_window,
)
from nsqd.domain.snapshot import canonical_json, is_utc_datetime, sha256_hex
from nsqd.domain.status import STATUS_WINDOW_DAYS, record_lifecycle, status_table, status_window

STATUS_WINDOW_REPLAY_PACKET_KIND = "status_window_calendar_replay_report"
SUMMARY_PACKET_KIND = "status_window_calendar_replay_summary"
EXPECTED_SNAPSHOT_ID = "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
EXPECTED_CORPUS_VERSION = 11
EXPECTED_RECORD_COUNT = 11
EXPECTED_FINANCE_RECORD_COUNT = 6
EXPECTED_OPTIMIZATION_RECORD_COUNT = 5
EXPECTED_HARVESTED_AT = "2026-09-02T06:45:00+00:00"
EXPECTED_SQLITE_SHA256 = "ab339287d8e9fcea662a1b8cb9557302bde356573cb4834a9b374a4cd375a2b7"
SEALED_AT_UTC = "2026-09-03T05:32:08Z"
EXPECTED_EXTRACTED_RECORDS_DIGEST = (
    "728c522334e7a64e91e32bba945a127a9ef958d915b75f0f09d2ea628b92b114"
)
CURRENT_AS_OF_SCENARIO_NOTE = (
    "observed report-as-of replay near the receipt-bound evidence timestamp"
)
BOUNDARY_SENSITIVITY_SCENARIO_NOTE = (
    "derived future sensitivity from the real receipt-bound harvested_at rows; "
    "not an observed future production state"
)
PROVENANCE_CAVEAT = (
    "timestamps are real persisted values from the receipt-bound report-only scratch replay, "
    "not proven original 2026-08-29 production-harvest timestamps because snapshot IDs "
    "do not bind harvested_at"
)


def extracted_records_digest(records: list[dict[str, Any]]) -> str:
    return sha256_hex(canonical_json(records))


def status_window_replay_artifact_digest(report: dict[str, Any]) -> str:
    body = {key: value for key, value in report.items() if key != "artifact_digest"}
    return sha256_hex(canonical_json(body))


def compare_status_window_semantics(
    records: list[dict[str, Any]],
    *,
    domain_policy_id: str,
    as_of: datetime,
    snapshot_state: str,
) -> dict[str, Any]:
    if not is_utc_datetime(as_of):
        raise ValueError("as_of must be a UTC datetime")
    fixed_window = status_window(STATUS_WINDOW_DAYS)
    calendar_window = calendar_month_window(as_of, months=CALENDAR_WINDOW_MONTHS)
    fixed_cutoff = as_of - fixed_window
    calendar_cutoff = calendar_month_cutoff(as_of, months=CALENDAR_WINDOW_MONTHS)
    policy_rows = [row for row in records if row.get("domain_policy_id") == domain_policy_id]
    lifecycle_rows: list[dict[str, Any]] = []
    fixed_life: list[str] = []
    calendar_life: list[str] = []
    for row in policy_rows:
        fixed = record_lifecycle(row, as_of=as_of, window=fixed_window)
        calendar = record_lifecycle(row, as_of=as_of, window=calendar_window)
        fixed_life.append(fixed)
        calendar_life.append(calendar)
        if fixed != calendar:
            lifecycle_rows.append(
                {
                    "record_id": str(row["record_id"]),
                    "source_paper_id": str(row["source_paper_id"]),
                    "harvested_at": str(row["harvested_at"]),
                    "fixed_lifecycle": fixed,
                    "calendar_lifecycle": calendar,
                }
            )
    fixed_statuses = status_table(
        records,
        domain_policy_id=domain_policy_id,
        as_of=as_of,
        snapshot_state=snapshot_state,
        window=fixed_window,
    )
    calendar_statuses = status_table(
        records,
        domain_policy_id=domain_policy_id,
        as_of=as_of,
        snapshot_state=snapshot_state,
        window=calendar_window,
    )
    changed_cells = [
        {
            "cell_id": cell_id,
            "fixed_status": fixed_statuses[cell_id],
            "calendar_status": calendar_statuses[cell_id],
        }
        for cell_id in fixed_statuses
        if fixed_statuses[cell_id] != calendar_statuses[cell_id]
    ]
    return {
        "domain_policy_id": domain_policy_id,
        "record_count": len(policy_rows),
        "fixed_cutoff_utc": fixed_cutoff.isoformat(),
        "calendar_cutoff_utc": calendar_cutoff.isoformat(),
        "fixed_window_days": STATUS_WINDOW_DAYS,
        "calendar_window_months": CALENDAR_WINDOW_MONTHS,
        "fixed_lifecycle_counts": dict(sorted(Counter(fixed_life).items())),
        "calendar_lifecycle_counts": dict(sorted(Counter(calendar_life).items())),
        "lifecycle_delta_count": len(lifecycle_rows),
        "lifecycle_delta_rows": lifecycle_rows,
        "fixed_cell_status_counts": dict(sorted(Counter(fixed_statuses.values()).items())),
        "calendar_cell_status_counts": dict(sorted(Counter(calendar_statuses.values()).items())),
        "cell_status_delta_count": len(changed_cells),
        "cell_status_delta_rows": changed_cells,
        "zero_delta": len(lifecycle_rows) == 0 and len(changed_cells) == 0,
    }


def derive_boundary_sensitivity_as_of(records: list[dict[str, Any]]) -> datetime:
    harvested_at = _expected_harvested_at_datetime(records)
    candidates = [
        _add_years_with_clamp(harvested_at, years=2),
        _add_years_with_clamp(harvested_at, years=2) + timedelta(days=1),
    ]
    for candidate in candidates:
        fixed_window = status_window(STATUS_WINDOW_DAYS)
        calendar_window = calendar_month_window(candidate, months=CALENDAR_WINDOW_MONTHS)
        if any(
            record_lifecycle(row, as_of=candidate, window=fixed_window)
            != record_lifecycle(row, as_of=candidate, window=calendar_window)
            for row in records
        ):
            return candidate
    raise ValueError(
        "could not derive a boundary sensitivity as_of from receipt-bound harvested_at rows"
    )


def build_status_window_replay_summary(
    artifact: dict[str, Any],
    *,
    rows_sha256: str,
    artifact_sha256: str,
) -> dict[str, Any]:
    validated = validate_status_window_replay_artifact(artifact)
    scenarios = _validated_scenarios_by_id(validated)
    current_policy_results = scenarios["current_as_of"]["policy_results"]
    boundary_sensitivity = scenarios["boundary_sensitivity"]
    calendar_months = _calendar_window_months_from_policy_results(current_policy_results)
    summary = {
        "schema_version": 1,
        "packet_kind": SUMMARY_PACKET_KIND,
        "authorization_state": str(validated["authorization_state"]),
        "runtime_authorized": validated["runtime_authorized"],
        "source_baseline_packet": (
            "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/baseline-evidence.json"
        ),
        "snapshot_id": str(validated["source_receipt"]["snapshot_id"]),
        "corpus_version": int(validated["source_receipt"]["corpus_version"]),
        "historical_receipt_verified_exact": validated["source_receipt"]["receipt_verified_exact"],
        "harvested_at_utc": str(validated["source_receipt"]["harvested_at_utc"]),
        "sealed_at_utc": str(validated["sealed_at_utc"]),
        "artifacts": {
            "extracted-timestamp-rows.json": rows_sha256,
            "calendar-replay-artifact.json": artifact_sha256,
        },
        "current_as_of_zero_delta": all(
            bool(current_policy_results[policy_id]["zero_delta"])
            for policy_id in ("finance/1", "optimization/1")
        ),
        "boundary_sensitivity_note": str(boundary_sensitivity["scenario_note"]),
        "runtime_status_window_days": int(validated["runtime_status_window_days"]),
        "calendar_window_months": calendar_months,
        "evidence_sufficient_scope": str(validated["evidence_sufficient_scope"]),
        "baseline_receipt_sqlite_sha256": str(validated["source_receipt"]["sqlite_sha256"]),
        "summary_digest": "",
    }
    summary["summary_digest"] = sha256_hex(
        canonical_json({key: value for key, value in summary.items() if key != "summary_digest"})
    )
    return summary


def validate_status_window_replay_artifact(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != 1:
        raise ValueError("schema_version is invalid")
    if report.get("packet_kind") != STATUS_WINDOW_REPLAY_PACKET_KIND:
        raise ValueError("packet_kind is invalid")
    if report.get("authorization_state") != "report_only":
        raise ValueError("authorization_state must be report_only")
    if report.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if report.get("evidence_sufficient") is not True:
        raise ValueError("evidence_sufficient must be true")
    if report.get("evidence_sufficient_scope") != "human_decision_only":
        raise ValueError("evidence_sufficient_scope must be human_decision_only")
    if report.get("runtime_status_window_days") != STATUS_WINDOW_DAYS:
        raise ValueError("runtime status window must remain 730 days")
    if report.get("sealed_at_utc") != SEALED_AT_UTC:
        raise ValueError("sealed_at_utc is invalid")
    if "generated_at_utc" in report:
        raise ValueError("generated_at_utc is not a valid sealed metadata field")
    if report.get("harvested_at_provenance_caveat") != PROVENANCE_CAVEAT:
        raise ValueError("harvested_at provenance caveat is invalid")
    if report.get("extracted_records_digest") != EXPECTED_EXTRACTED_RECORDS_DIGEST:
        raise ValueError(
            "extracted_records_digest does not match the sealed approved snapshot rows"
        )
    extracted_rows = report.get("extracted_records")
    if not isinstance(extracted_rows, list):
        raise ValueError("extracted_records are required")
    records = _require_extracted_records(extracted_rows)
    receipt = report.get("source_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("source_receipt is required")
    if receipt != {
        "snapshot_id": EXPECTED_SNAPSHOT_ID,
        "corpus_version": EXPECTED_CORPUS_VERSION,
        "record_count": EXPECTED_RECORD_COUNT,
        "sqlite_sha256": EXPECTED_SQLITE_SHA256,
        "harvested_at_utc": EXPECTED_HARVESTED_AT,
        "receipt_verified_exact": True,
    }:
        raise ValueError("source_receipt does not match the verified historical scratch receipt")
    scenarios = report.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 2:
        raise ValueError("scenarios must contain the current and boundary sensitivity comparisons")
    expected_current_as_of = _expected_harvested_at_datetime(records)
    expected_boundary_as_of = derive_boundary_sensitivity_as_of(records)
    scenario_by_id = {str(item.get("scenario_id")): item for item in scenarios}
    required = {"current_as_of", "boundary_sensitivity"}
    if set(scenario_by_id) != required:
        raise ValueError("scenarios must contain current_as_of and boundary_sensitivity ids")
    _validate_scenario(
        scenario_by_id["current_as_of"],
        records,
        as_of=expected_current_as_of,
        scenario_kind="observed_current_as_of",
    )
    _validate_scenario(
        scenario_by_id["boundary_sensitivity"],
        records,
        as_of=expected_boundary_as_of,
        scenario_kind="boundary_sensitivity",
    )
    if status_window_replay_artifact_digest(report) != report.get("artifact_digest"):
        raise ValueError("artifact_digest does not match canonical replay artifact content")
    return report


def _validate_scenario(
    scenario: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    as_of: datetime,
    scenario_kind: str,
) -> None:
    if scenario.get("scenario_kind") != scenario_kind:
        raise ValueError("scenario_kind is invalid")
    expected_note = (
        CURRENT_AS_OF_SCENARIO_NOTE
        if scenario_kind == "observed_current_as_of"
        else BOUNDARY_SENSITIVITY_SCENARIO_NOTE
    )
    if scenario.get("scenario_note") != expected_note:
        raise ValueError("scenario_note is invalid")
    if scenario.get("as_of_utc") != as_of.isoformat():
        raise ValueError("scenario as_of_utc does not match the derived replay input")
    policy_results = scenario.get("policy_results")
    if not isinstance(policy_results, dict) or set(policy_results) != {
        "finance/1",
        "optimization/1",
    }:
        raise ValueError("policy_results must contain finance/1 and optimization/1 only")
    for policy_id in ("finance/1", "optimization/1"):
        expected = compare_status_window_semantics(
            records,
            domain_policy_id=policy_id,
            as_of=as_of,
            snapshot_state="production_valid",
        )
        if policy_results[policy_id] != expected:
            raise ValueError(
                f"policy_results[{policy_id}] does not match recomputed comparison output"
            )


def _require_extracted_records(rows: list[object]) -> list[dict[str, Any]]:
    if len(rows) != EXPECTED_RECORD_COUNT:
        raise ValueError("extracted_records must contain exactly 11 snapshot members")
    normalized: list[dict[str, Any]] = []
    harvested = set()
    record_ids: list[str] = []
    policy_counts = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("extracted_records must be mappings")
        typed_row = {str(key): value for key, value in row.items()}
        record_id = str(typed_row.get("record_id") or "")
        if not record_id:
            raise ValueError("extracted_records record_id is required")
        record_ids.append(record_id)
        policy_id = str(typed_row.get("domain_policy_id") or "")
        policy_counts[policy_id] += 1
        harvested_at = typed_row.get("harvested_at")
        if harvested_at != EXPECTED_HARVESTED_AT:
            raise ValueError(
                "harvested_at rows must match the observed receipt-bound UTC timestamp"
            )
        harvested.add(harvested_at)
        normalized.append(typed_row)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("extracted_records record ids must be unique")
    if harvested != {EXPECTED_HARVESTED_AT}:
        raise ValueError("all extracted_records must share the observed harvested_at timestamp")
    if policy_counts != {
        "finance/1": EXPECTED_FINANCE_RECORD_COUNT,
        "optimization/1": EXPECTED_OPTIMIZATION_RECORD_COUNT,
    }:
        raise ValueError("extracted_records must contain exactly 6 finance and 5 optimization rows")
    if extracted_records_digest(normalized) != EXPECTED_EXTRACTED_RECORDS_DIGEST:
        raise ValueError(
            "extracted_records_digest does not match the sealed approved snapshot rows"
        )
    return normalized


def _expected_harvested_at_datetime(records: list[dict[str, Any]]) -> datetime:
    if not records:
        raise ValueError("records are required")
    harvested_at = records[0]["harvested_at"]
    parsed = datetime.fromisoformat(str(harvested_at).replace("Z", "+00:00"))
    if not is_utc_datetime(parsed):
        raise ValueError("harvested_at must be a UTC datetime")
    return parsed


def _add_years_with_clamp(value: datetime, *, years: int) -> datetime:
    target_year = value.year + years
    day = value.day
    while day > 28:
        try:
            return value.replace(year=target_year, day=day)
        except ValueError:
            day -= 1
    return value.replace(year=target_year, day=day)


def _validated_scenarios_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenarios = artifact["scenarios"]
    assert isinstance(scenarios, list)
    return {str(item["scenario_id"]): item for item in scenarios if isinstance(item, dict)}


def _calendar_window_months_from_policy_results(policy_results: Any) -> int:
    if not isinstance(policy_results, dict):
        raise ValueError("policy_results are required for summary derivation")
    months = {
        int(policy_results[policy_id]["calendar_window_months"])
        for policy_id in ("finance/1", "optimization/1")
    }
    if len(months) != 1:
        raise ValueError("calendar_window_months must agree across policy results")
    return next(iter(months))
