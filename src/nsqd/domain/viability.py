from __future__ import annotations

from typing import Any

from nsqd.domain.snapshot import is_utc_datetime_or_iso

_FINANCE_MECH_FIELDS = (
    "mechanism",
    "inefficiency",
    "counterparty",
    "persistence",
    "capacity",
    "regime_dependence",
)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def score_mech(candidate: dict[str, Any], *, domain_pack: str) -> int:
    if domain_pack.startswith("finance"):
        if any(_is_empty(candidate.get(field)) for field in _FINANCE_MECH_FIELDS):
            return 0
        return 5
    return 0


def score_fals(candidate: dict[str, Any]) -> int:
    if _is_empty(candidate.get("cheapest_falsifier")) or _is_empty(candidate.get("kill_criteria")):
        return 0
    return 5


def score_dpred(candidate: dict[str, Any]) -> int:
    return 0 if _is_empty(candidate.get("differential_prediction")) else 5


def score_dval(candidate: dict[str, Any]) -> int:
    assignment = candidate.get("dval")
    if not isinstance(assignment, dict):
        return 0
    if _is_empty(assignment.get("assigned_by")) or _is_empty(assignment.get("rubric_id")):
        return 0
    if not is_utc_datetime_or_iso(assignment.get("assigned_at")):
        return 0
    value = assignment.get("value")
    if not isinstance(value, int) or value < 0 or value > 5:
        return 0
    return value


def viability(
    *,
    nov: int,
    mech: int,
    fals: int,
    dpred: int,
    dval: int,
) -> int:
    return nov * mech * fals * dpred * dval
