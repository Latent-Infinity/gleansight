from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from nsqd.domain.status import CellStatus

PREFERRED_TARGET_STATUSES = frozenset({"Missing", "Sparse", "Code-gap", "Benchmark-gap", "Stalled"})


def select_target_cell(
    cell_statuses: dict[str, CellStatus],
    *,
    elite_viability: Mapping[str, int] | None = None,
) -> str:
    if not cell_statuses:
        raise ValueError("cell_statuses must not be empty")
    elites = dict(elite_viability or {})
    preferred = [
        cell_id
        for cell_id, status in cell_statuses.items()
        if status in PREFERRED_TARGET_STATUSES and cell_id not in elites
    ]
    if preferred:
        return min(preferred)
    scoped = {
        cell_id: viability for cell_id, viability in elites.items() if cell_id in cell_statuses
    }
    if scoped:
        return min(scoped, key=lambda cell_id: (scoped[cell_id], cell_id))
    return min(cell_statuses)


def require_operator_a(operator: str) -> Literal["A"]:
    if operator != "A":
        raise ValueError("baseline requires Operator A")
    return "A"


def normalize_axiom_rows(axioms: list[Any]) -> list[dict[str, str]]:
    if not isinstance(axioms, list) or not axioms:
        raise ValueError("axiom list is required")
    rows: list[dict[str, str]] = []
    for item in axioms:
        extra: dict[str, str] = {}
        if isinstance(item, str):
            statement = item.strip()
        elif isinstance(item, dict):
            raw = item.get("statement")
            statement = raw.strip() if isinstance(raw, str) else ""
            cell_id = item.get("cell_id")
            if cell_id is not None and (not isinstance(cell_id, str) or not cell_id.strip()):
                raise ValueError("cell_id must be a non-empty string")
            if isinstance(cell_id, str) and cell_id.strip():
                extra["cell_id"] = cell_id.strip()
        else:
            raise ValueError("axiom statement is required")
        if not statement:
            raise ValueError("axiom statement is required")
        rows.append({"statement": statement, **extra})
    return rows


def require_elite_viability(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 25:
        raise ValueError("elite viability must be a non-bool int in 0..25")
    return value


def parent_card_id_for_target(
    *,
    elite_card_id: str | None,
    parent_card_id: str | None,
) -> str | None:
    if elite_card_id is None:
        if parent_card_id is not None:
            raise ValueError("empty target cell has no parent card")
        return None
    if parent_card_id is None:
        return None
    if parent_card_id != elite_card_id:
        raise ValueError("parent_card_id must be the target cell elite")
    return parent_card_id
