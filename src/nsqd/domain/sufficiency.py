from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from nsqd.domain.policy import DomainPolicy, records_for_policy
from nsqd.domain.snapshot import normalize_source
from nsqd.domain.status import record_lifecycle

SufficiencyFailure = Literal[
    "expected_cell_empty",
    "recall_probe_missing",
    "disagreement_unresolved",
    "record_metadata_missing",
    "duplicate_source_conflict",
    "retracted_unmarked",
    "domain_minima_unmet",
    "manifest_missing",
]

SUFFICIENCY_FAILURES = frozenset(
    {
        "expected_cell_empty",
        "recall_probe_missing",
        "disagreement_unresolved",
        "record_metadata_missing",
        "duplicate_source_conflict",
        "retracted_unmarked",
        "domain_minima_unmet",
        "manifest_missing",
    }
)
SEARCHABLE_FAILURES = frozenset(
    {"expected_cell_empty", "recall_probe_missing", "domain_minima_unmet"}
)
INTEGRITY_FAILURES = frozenset(
    {
        "manifest_missing",
        "record_metadata_missing",
        "duplicate_source_conflict",
        "retracted_unmarked",
        "disagreement_unresolved",
    }
)
CALIBRATION_ALLOWED_FAILURES = frozenset({"expected_cell_empty", "domain_minima_unmet"})
_FAILURE_ORDER = (
    "manifest_missing",
    "record_metadata_missing",
    "duplicate_source_conflict",
    "retracted_unmarked",
    "disagreement_unresolved",
    "recall_probe_missing",
    "expected_cell_empty",
    "domain_minima_unmet",
)


def evaluate_sufficiency(
    records: list[dict[str, Any]],
    *,
    policy: DomainPolicy,
    as_of: datetime,
    disagreement: bool = False,
    approved_manifest: bool = True,
) -> tuple[SufficiencyFailure, ...]:
    found: set[SufficiencyFailure] = set()
    if not approved_manifest:
        found.add("manifest_missing")
        return _ordered(found)
    scoped = records_for_policy(records, policy.policy_id)
    if disagreement:
        found.add("disagreement_unresolved")
    paraphrases_by_source: dict[str, str] = {}
    for row in scoped:
        if _metadata_missing(row):
            found.add("record_metadata_missing")
            continue
        if row.get("retraction_notice") and row.get("retracted") is not True:
            found.add("retracted_unmarked")
        source = normalize_source(str(row["source"]))
        paraphrase = str(row["paraphrase"])
        previous = paraphrases_by_source.get(source)
        if previous is not None and previous != paraphrase:
            found.add("duplicate_source_conflict")
        else:
            paraphrases_by_source[source] = paraphrase
    context = sufficiency_search_context(scoped, policy=policy, as_of=as_of)
    if context["missing_recall_probes"]:
        found.add("recall_probe_missing")
    if context["missing_cell_ids"]:
        found.add("expected_cell_empty")
    if context["domain_minima_unmet"]:
        found.add("domain_minima_unmet")
    return _ordered(found)


def sufficiency_search_context(
    records: list[dict[str, Any]],
    *,
    policy: DomainPolicy,
    as_of: datetime,
) -> dict[str, Any]:
    scoped = records_for_policy(records, policy.policy_id)
    type_counts = {"paper": 0, "code": 0, "benchmark": 0}
    occupied_cells: set[str] = set()
    for row in scoped:
        if _metadata_missing(row) or record_lifecycle(row, as_of=as_of) == "invalid":
            continue
        rec_type = str(row["type"])
        if rec_type in type_counts:
            type_counts[rec_type] += 1
        coords = row.get("coordinates")
        if isinstance(coords, dict):
            try:
                occupied_cells.add(policy.cell_id(coords))
            except ValueError:
                pass
    missing_probes = [
        {"probe_id": probe_id, "source": source, "record_type": expected_type}
        for probe_id, source, expected_type in policy.recall_probes
        if not _probe_present(
            scoped,
            source=source,
            expected_type=expected_type,
            as_of=as_of,
        )
    ]
    unmet_record_types = sorted(
        str(rec_type)
        for rec_type, minimum in policy.required_record_types.items()
        if type_counts.get(str(rec_type), 0) < int(minimum)
    )
    total_unmet = sum(type_counts.values()) < policy.min_records
    return {
        "missing_cell_ids": sorted(policy.expected_cells - occupied_cells),
        "missing_recall_probes": missing_probes,
        "unmet_record_types": unmet_record_types,
        "domain_minima_unmet": total_unmet or bool(unmet_record_types),
    }


def decide_snapshot_state(
    failures: tuple[str, ...] | list[str],
    *,
    target: str,
    domain_policy_id: str = "",
    harvest_seed_approved: bool = False,
    recall_probe_listed: bool = True,
) -> str:
    codes = tuple(failures)
    if target == "production_valid":
        if domain_policy_id == "finance/1" and not harvest_seed_approved:
            return "insufficient"
        return "production_valid" if not codes else "insufficient"
    if target == "calibration":
        if not recall_probe_listed:
            return "insufficient"
        blocking = [code for code in codes if code not in CALIBRATION_ALLOWED_FAILURES]
        return "calibration" if not blocking else "insufficient"
    raise ValueError("invalid snapshot_state: expected one of calibration, production_valid")


def _ordered(found: set[SufficiencyFailure]) -> tuple[SufficiencyFailure, ...]:
    return tuple(code for code in _FAILURE_ORDER if code in found)


def _metadata_missing(row: dict[str, Any]) -> bool:
    rec_type = row.get("type")
    paraphrase = row.get("paraphrase")
    source = row.get("source")
    content_hash = row.get("content_hash")
    return not (
        isinstance(rec_type, str)
        and rec_type.strip()
        and isinstance(paraphrase, str)
        and paraphrase.strip()
        and isinstance(source, str)
        and source.strip()
        and isinstance(content_hash, str)
        and content_hash.strip()
    )


def _probe_present(
    records: list[dict[str, Any]],
    *,
    source: str,
    expected_type: str,
    as_of: datetime,
) -> bool:
    wanted = normalize_source(source)
    for row in records:
        if _metadata_missing(row):
            continue
        if record_lifecycle(row, as_of=as_of) == "invalid":
            continue
        if str(row.get("type")) != expected_type:
            continue
        if normalize_source(str(row["source"])) == wanted:
            return True
    return False
