from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
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


OPERATOR_IDS = ("A", "B", "C", "D", "E", "F", "G")
DEFAULT_ENABLED_OPERATORS = frozenset({"A"})
OperatorActivation = Literal["supported", "experimental", "deferred"]
SupportedOperator = Literal["A", "B"]


@dataclass(frozen=True)
class OperatorDecision:
    operator_id: str
    activation: OperatorActivation
    runtime_enabled: bool
    wait_on: str


def operator_decisions() -> tuple[OperatorDecision, ...]:
    return (
        OperatorDecision("A", "supported", True, ""),
        OperatorDecision(
            "B",
            "supported",
            True,
            "non-default; enabled only by the composition allowlist",
        ),
        OperatorDecision(
            "C",
            "deferred",
            False,
            "two named literatures after B is activated",
        ),
        OperatorDecision(
            "D",
            "deferred",
            False,
            "source and target domain_policy_id after C",
        ),
        OperatorDecision(
            "E",
            "deferred",
            False,
            "packet 2b executable novelty threshold if E uses novelty as a kill",
        ),
        OperatorDecision(
            "F",
            "deferred",
            False,
            "axis-policy clarity for proposing an unlisted archive dimension",
        ),
        OperatorDecision(
            "G",
            "deferred",
            False,
            "approved failed-experiment corpus; do not invent failure records",
        ),
    )


def operator_is_enabled(
    operator_id: str,
    *,
    enabled_operators: frozenset[str] = DEFAULT_ENABLED_OPERATORS,
) -> bool:
    for row in operator_decisions():
        if row.operator_id == operator_id:
            return row.runtime_enabled and operator_id in enabled_operators
    raise ValueError(f"unknown operator: {operator_id}")


def require_enabled_operators(
    enabled_operators: Iterable[str] | None = None,
) -> frozenset[str]:
    if enabled_operators is None:
        return DEFAULT_ENABLED_OPERATORS
    if isinstance(enabled_operators, (str, bytes, Mapping)):
        raise ValueError("enabled_operators must be an iterable of operator ids")
    unique = frozenset(enabled_operators)
    if "A" not in unique:
        raise ValueError("composition allowlist must include Operator A")
    decisions = {row.operator_id: row for row in operator_decisions()}
    for operator_id in unique:
        row = decisions.get(operator_id)
        if row is None:
            raise ValueError(f"unknown operator: {operator_id}")
        if operator_id not in {"A", "B"} or not row.runtime_enabled:
            raise ValueError(f"operator {operator_id} is not supported")
    return unique


def enabled_operators_from_settings(settings: object | None) -> frozenset[str]:
    nsqd = getattr(settings, "nsqd", None)
    raw = getattr(nsqd, "enabled_operators", None)
    if raw is None:
        return DEFAULT_ENABLED_OPERATORS
    return require_enabled_operators(raw)


def require_operator_a(operator: str) -> Literal["A"]:
    if operator != "A" or not operator_is_enabled(operator):
        raise ValueError("baseline requires Operator A")
    return "A"


def require_operator(
    operator: str,
    *,
    enabled_operators: frozenset[str] = DEFAULT_ENABLED_OPERATORS,
) -> SupportedOperator:
    allowlist = require_enabled_operators(enabled_operators)
    if operator not in {"A", "B"}:
        if operator not in OPERATOR_IDS:
            raise ValueError(f"unknown operator: {operator}")
        raise ValueError(f"operator {operator} is not supported")
    if not operator_is_enabled(operator, enabled_operators=allowlist):
        raise ValueError(f"operator {operator} is not enabled by composition")
    if operator == "A":
        return "A"
    return "B"


def whitespace_cells(
    cell_statuses: dict[str, CellStatus],
    *,
    elite_viability: Mapping[str, int] | None = None,
) -> tuple[str, ...]:
    elites = dict(elite_viability or {})
    return tuple(
        sorted(
            cell_id
            for cell_id, status in cell_statuses.items()
            if status in PREFERRED_TARGET_STATUSES and cell_id not in elites
        )
    )


def require_operator_b_target(
    cell_id: str,
    cell_statuses: dict[str, CellStatus],
    *,
    elite_viability: Mapping[str, int] | None = None,
) -> str:
    selected = select_target_cell(cell_statuses, elite_viability=elite_viability)
    if cell_id != selected:
        raise ValueError("Operator B target must match ALG-SEL")
    return selected


def require_no_axiom_inversion(
    *,
    candidate: Mapping[str, Any] | None = None,
    axioms: list[Any] | None = None,
) -> None:
    if candidate is not None and candidate.get("inversion") is True:
        raise ValueError("Operator B cannot invert axioms")
    for item in axioms or []:
        if isinstance(item, dict) and item.get("inverted") is True:
            raise ValueError("Operator B cannot invert axioms")


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
