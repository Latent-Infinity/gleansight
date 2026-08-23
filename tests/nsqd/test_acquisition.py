from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nsqd.composition import build_container
from nsqd.domain.acquisition import (
    CANDIDATES_PER_BATCH,
    QUERY_BATCH_LIMIT,
    RECHECK_CYCLE_LIMIT,
    STAGED_IMPORT_LIMIT,
    acquisition_cycle_id,
    acquisition_route,
    render_acquisition_query,
)
from nsqd.domain.policy import FINANCE_POLICY
from nsqd.null_adapters import FixedClock
from nsqd.runner import run_job
from tests.facts.test_nsqd_acquisition_fallback import FakePaperBridge

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIN_CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"


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


def _search_policy() -> Any:
    return replace(
        FINANCE_POLICY,
        expected_cells=frozenset({FIN_CELL}),
        recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
    )


def test_acquire_handler_and_runner_persist_and_dispatch(tmp_path: Path) -> None:
    container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
    )
    policy = _search_policy()
    container.ctx.bridge = FakePaperBridge([{"paper_id": "p1", "title": "A"}])
    container.ctx.policies = {policy.policy_id: policy}
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    result = run_job(
        container,
        "acquire",
        {
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "target": "calibration",
        },
        AS_OF,
    )

    assert result["status"] == "succeeded"
    assert result["stopped"] == "pending_human_approval"
    assert result["projected"] is False
    job_row = container.database.fetchone(
        "SELECT status, payload_json FROM nsqd_jobs WHERE type = 'acquire'"
    )
    assert job_row is not None
    assert job_row["status"] == "succeeded"
    assert container.ctx.cycles is not None
    stored = container.ctx.cycles.get(str(result["cycle_id"]))
    assert stored is not None
    assert stored["stopped"] == "pending_human_approval"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"domain_policy_id": "finance/1", "target": "calibration"},
            "snapshot_id is required",
        ),
        ({"snapshot_id": "snap", "target": "calibration"}, "domain_policy_id is required"),
        ({"snapshot_id": "snap", "domain_policy_id": "finance/1"}, "target is required"),
        (
            {
                "snapshot_id": "snap",
                "domain_policy_id": "finance/1",
                "target": "calibration",
                "human_decision": 1,
            },
            "human_decision must be a string",
        ),
        (
            {
                "snapshot_id": "snap",
                "domain_policy_id": "finance/1",
                "target": "calibration",
                "approved_projections": "nope",
            },
            "approved_projections must be a list",
        ),
    ],
)
def test_acquire_runner_rejects_malformed_payload(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    container = build_container(
        db_path=tmp_path / "bad-acquire.sqlite",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
    )
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    with pytest.raises(ValueError, match=message):
        run_job(container, "acquire", payload, AS_OF)

    job_row = container.database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs ORDER BY created_at DESC LIMIT 1"
    )
    assert job_row is not None
    assert job_row["status"] == "failed"


def test_acquire_restart_reuses_fail_closed_cycle(tmp_path: Path) -> None:
    container = build_container(
        db_path=tmp_path / "retry-acquire.sqlite",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
    )
    policy = _search_policy()
    bridge = FakePaperBridge([{"paper_id": "p1", "title": "A"}], fail_stage=True)
    container.ctx.bridge = bridge
    container.ctx.policies = {policy.policy_id: policy}
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1
    payload = {
        "snapshot_id": "snap",
        "domain_policy_id": "finance/1",
        "target": "calibration",
    }

    with pytest.raises(RuntimeError, match="staging failed"):
        run_job(container, "acquire", payload, AS_OF)
    assert container.ctx.cycles is not None
    stored = next(
        iter(container.database.fetchall("SELECT payload_json FROM nsqd_acquisition_cycles"))
    )
    assert "manual_recovery" in str(stored["payload_json"])
    discover_calls = bridge.discover_calls

    repeated = run_job(container, "acquire", payload, AS_OF)
    assert repeated["stopped"] == "manual_recovery"
    assert bridge.discover_calls == discover_calls
