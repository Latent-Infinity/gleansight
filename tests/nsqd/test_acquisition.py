from __future__ import annotations

from nsqd.domain.acquisition import (
    CANDIDATES_PER_BATCH,
    QUERY_BATCH_LIMIT,
    RECHECK_CYCLE_LIMIT,
    STAGED_IMPORT_LIMIT,
    acquisition_cycle_id,
    acquisition_route,
    render_acquisition_query,
)


def test_integrity_failures_stop_for_manual_review() -> None:
    assert acquisition_route(("record_metadata_missing",)) == "manual"
    assert acquisition_route(("duplicate_source_conflict", "expected_cell_empty")) == "manual"


def test_searchable_failures_route_to_search() -> None:
    assert acquisition_route(("expected_cell_empty",)) == "search"
    assert acquisition_route(("recall_probe_missing", "domain_minima_unmet")) == "search"


def test_no_failures_stop() -> None:
    assert acquisition_route(()) == "stop"


def test_query_plan_is_deterministic() -> None:
    first = render_acquisition_query(
        policy_id="finance/1",
        failure="expected_cell_empty",
        cell_id="mechanism=flow-driven|target=drawdown|horizon=intraday",
        record_type="paper",
    )
    second = render_acquisition_query(
        policy_id="finance/1",
        failure="expected_cell_empty",
        cell_id="mechanism=flow-driven|target=drawdown|horizon=intraday",
        record_type="paper",
    )
    assert first == second
    assert "finance/1" in first
    assert "expected_cell_empty" in first


def test_cycle_identity_is_stable_and_sensitive() -> None:
    kwargs = {
        "snapshot_id": "snap",
        "domain_policy_id": "finance/1",
        "failure_signature": ("expected_cell_empty",),
        "rendered_query": "finance/1 expected_cell_empty",
        "filters": {"type": "paper"},
    }
    first = acquisition_cycle_id(**kwargs)
    second = acquisition_cycle_id(**kwargs)
    assert first == second
    other = acquisition_cycle_id(**{**kwargs, "snapshot_id": "other"})
    assert other != first


def test_acquisition_bounds() -> None:
    assert QUERY_BATCH_LIMIT == 3
    assert CANDIDATES_PER_BATCH == 25
    assert STAGED_IMPORT_LIMIT == 3
    assert RECHECK_CYCLE_LIMIT == 2
