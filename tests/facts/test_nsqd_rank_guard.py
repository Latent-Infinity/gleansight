from __future__ import annotations

from types import MappingProxyType
from typing import cast

import pytest

from nsqd.app.use_cases import RankArchiveUseCase
from nsqd.domain.coverage import RankGuardBlocked, archive_coverage, evaluate_rank_guard
from nsqd.domain.descriptor import finance_pack_universe
from nsqd.domain.status import CellStatus


def _cells(count: int) -> set[str]:
    universe = sorted(finance_pack_universe())
    return set(universe[:count])


def _use_case(*, invalid: set[str] | None = None) -> RankArchiveUseCase:
    statuses: dict[str, CellStatus] = {cell_id: "Invalid" for cell_id in invalid or set()}
    return RankArchiveUseCase(cell_statuses=statuses)


def test_finance_pack_universe_has_336_cells() -> None:
    assert len(finance_pack_universe()) == 336


def test_rank_blocked_below_both_thresholds() -> None:
    use_case = _use_case()
    with pytest.raises(RankGuardBlocked, match="rank_guard_blocked"):
        use_case.run(elite_cell_ids=_cells(0))


def test_rank_blocked_at_49_elites_when_coverage_below_20_percent() -> None:
    use_case = _use_case()
    elites = _cells(49)
    eligible = len(finance_pack_universe())
    assert archive_coverage(elite_count=49, eligible_universe=eligible) < 0.20
    with pytest.raises(RankGuardBlocked, match="rank_guard_blocked"):
        use_case.run(elite_cell_ids=elites)


def test_rank_allowed_at_50_elites_even_when_coverage_below_20_percent() -> None:
    use_case = _use_case()
    result = use_case.run(elite_cell_ids=_cells(50))
    assert result["allowed"] is True
    assert result["elite_count"] == 50
    assert result["coverage"] < 0.20


def test_rank_allowed_at_exactly_20_percent_coverage_with_fewer_than_50_elites() -> None:
    universe = sorted(finance_pack_universe())
    invalid = set(universe[45:])
    elites = set(universe[:9])
    assert len(invalid) == 291
    assert archive_coverage(elite_count=9, eligible_universe=45) == 0.20
    result = _use_case(invalid=invalid).run(elite_cell_ids=elites)
    assert result["allowed"] is True
    assert result["elite_count"] == 9
    assert result["coverage"] == 0.20


def test_unknown_uninspected_cells_stay_in_denominator() -> None:
    with pytest.raises(RankGuardBlocked, match="rank_guard_blocked"):
        _use_case().run(elite_cell_ids=_cells(1))


def test_invalid_elite_cells_are_excluded_from_the_numerator() -> None:
    universe = sorted(finance_pack_universe())
    invalid = {universe[0]}
    result = _use_case(invalid=invalid).run(elite_cell_ids=set(universe[:51]))

    assert result["elite_count"] == 50
    assert result["eligible_universe"] == 335
    assert result["coverage"] == 50 / 335


def test_all_invalid_cells_leave_an_empty_eligible_universe() -> None:
    universe = finance_pack_universe()
    with pytest.raises(RankGuardBlocked, match="rank_guard_blocked"):
        _use_case(invalid=set(universe)).run(elite_cell_ids=set(universe))


def test_rank_guard_rejects_non_builtin_collections() -> None:
    elite_generator = cast(set[str], iter(finance_pack_universe()))
    with pytest.raises(TypeError, match="elite_cell_ids must be a set or frozenset"):
        evaluate_rank_guard(elite_cell_ids=elite_generator, cell_statuses={})

    proxy = cast(dict[str, CellStatus], MappingProxyType({}))
    with pytest.raises(TypeError, match="cell_statuses must be a dict"):
        evaluate_rank_guard(elite_cell_ids=set(), cell_statuses=proxy)


def test_rank_guard_rejects_inputs_larger_than_the_universe() -> None:
    oversized_elites = {f"unknown-{index}" for index in range(337)}
    with pytest.raises(ValueError, match="elite_cell_ids exceeds the descriptor universe"):
        evaluate_rank_guard(elite_cell_ids=oversized_elites, cell_statuses={})

    oversized_statuses: dict[str, CellStatus] = {
        f"unknown-{index}": "Unknown" for index in range(337)
    }
    with pytest.raises(ValueError, match="cell_statuses exceeds the descriptor universe"):
        evaluate_rank_guard(elite_cell_ids=set(), cell_statuses=oversized_statuses)
