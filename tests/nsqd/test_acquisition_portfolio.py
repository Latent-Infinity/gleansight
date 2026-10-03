from __future__ import annotations

import pytest

from nsqd.app.portfolio.planning import plan_portfolio
from nsqd.domain.acquisition_portfolio import PortfolioCaps, SufficiencyObservation


def observation() -> SufficiencyObservation:
    return SufficiencyObservation.model_validate(
        {
            "snapshot_id": "initial",
            "domain_policy_id": "finance/1",
            "target": "calibration",
            "state": "insufficient",
            "failures": ["recall_probe_missing", "expected_cell_empty", "domain_minima_unmet"],
            "search_context": {
                "missing_cell_ids": ["cell-b", "cell-a"],
                "missing_recall_probes": [
                    {"probe_id": "p", "source": "doi:1", "record_type": "paper"}
                ],
                "unmet_record_types": ["paper", "code"],
                "domain_minima_unmet": True,
            },
        }
    )


def test_portfolio_covers_sorted_unique_deficits_and_enforces_global_caps() -> None:
    before = observation()
    plan = plan_portfolio(before, PortfolioCaps(max_deficits=4, max_queries=3))
    assert len(plan.deficits) == 3
    assert len(plan.queries) == 3
    assert len(set(item.deficit_id for item in plan.deficits)) == 3
    assert all(query.target_ids for query in plan.queries)
    shuffled = before.model_copy(
        update={
            "failures": tuple(reversed(before.failures)),
            "search_context": before.search_context.model_copy(
                update={"missing_cell_ids": tuple(reversed(before.search_context.missing_cell_ids))}
            ),
        }
    )
    assert plan_portfolio(shuffled, plan.caps) == plan
    assert len(plan_portfolio(before, PortfolioCaps()).deficits) == 5


def test_integrity_failure_routes_to_manual_without_any_search() -> None:
    before = observation().model_copy(
        update={"failures": ("record_metadata_missing", "expected_cell_empty")}
    )
    plan = plan_portfolio(before, PortfolioCaps())
    assert plan.route == "manual" and not plan.queries and not plan.deficits


def test_zero_or_unbounded_caps_are_rejected() -> None:
    for values in ({"max_sources": 0}, {"per_deficit_sources": 10000}, {"max_queries": 0}):
        with pytest.raises(ValueError):
            PortfolioCaps.model_validate(values)


def test_overlapping_retrievals_import_once_and_keep_each_target_binding() -> None:
    from nsqd.app.portfolio.staging import stage_portfolio
    from tests.facts.test_nsqd_acquisition_fallback import FakePaperBridge

    bridge = FakePaperBridge(
        [{"source_paper_id": "a", "title": "A"}, {"source_paper_id": "b", "title": "B"}]
    )
    plan = plan_portfolio(observation(), PortfolioCaps(max_sources=1, per_deficit_sources=1))
    staged = stage_portfolio(plan, bridge)
    assert len(staged.sources) == 1
    assert set(staged.sources[0].target_ids) == {item.deficit_id for item in plan.deficits}
    assert len(staged.retrievals) == len(plan.queries)
    assert all(row.shortlisted_source_ids == ("a",) for row in staged.retrievals)
    assert len(bridge.staged) == 1
