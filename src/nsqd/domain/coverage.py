from __future__ import annotations

from nsqd.domain.descriptor import finance_pack_universe
from nsqd.domain.status import CellStatus

ELITE_FLOOR = 50
COVERAGE_FLOOR = 0.20


class RankGuardBlocked(ValueError):
    """Global rank is blocked until ALG-COV thresholds are met."""


def archive_coverage(*, elite_count: int, eligible_universe: int) -> float:
    return elite_count / max(1, eligible_universe)


def rank_allowed(*, elite_count: int, eligible_universe: int) -> bool:
    coverage = archive_coverage(elite_count=elite_count, eligible_universe=eligible_universe)
    return elite_count >= ELITE_FLOOR or coverage >= COVERAGE_FLOOR


def evaluate_rank_guard(
    *,
    elite_cell_ids: set[str] | frozenset[str],
    cell_statuses: dict[str, CellStatus],
) -> dict[str, float | int | bool]:
    universe = finance_pack_universe()
    if type(elite_cell_ids) not in {set, frozenset}:
        raise TypeError("elite_cell_ids must be a set or frozenset")
    if type(cell_statuses) is not dict:
        raise TypeError("cell_statuses must be a dict")
    if len(elite_cell_ids) > len(universe):
        raise ValueError("elite_cell_ids exceeds the descriptor universe")
    if len(cell_statuses) > len(universe):
        raise ValueError("cell_statuses exceeds the descriptor universe")
    invalid = {
        cell_id for cell_id, status in cell_statuses.items() if status == "Invalid"
    } & universe
    eligible = universe - invalid
    elites = elite_cell_ids & eligible
    elite_count = len(elites)
    eligible_universe = len(eligible)
    coverage = archive_coverage(elite_count=elite_count, eligible_universe=eligible_universe)
    if not rank_allowed(elite_count=elite_count, eligible_universe=eligible_universe):
        raise RankGuardBlocked("rank_guard_blocked")
    return {
        "allowed": True,
        "elite_count": elite_count,
        "eligible_universe": eligible_universe,
        "coverage": coverage,
    }
