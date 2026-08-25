from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nsqd.app.use_cases import MapSnapshotUseCase, RankArchiveUseCase
from nsqd.composition import build_container
from nsqd.domain.coverage import RankGuardBlocked
from nsqd.domain.policy import UnknownDomainPolicy, archive_cell_key
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullMorphospaceStore,
)
from nsqd.runner import run_job

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
RECENT = AS_OF - timedelta(days=10)
FINANCE_CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"
FINANCE_COORDS = {
    "mechanism": "flow-driven",
    "target": "drawdown",
    "horizon": "intraday",
}
OPT_CELL = "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"
OPT_COORDS = {
    "problem": "constrained-expectation",
    "method": "sequential-quadratic",
    "setting": "rank-deficient",
}


def _stores() -> tuple[NullCorpusRecordStore, NullCorpusSnapshotStore, NullMorphospaceStore]:
    return NullCorpusRecordStore(), NullCorpusSnapshotStore(), NullMorphospaceStore()


def _put(
    records: NullCorpusRecordStore,
    record_id: str,
    *,
    rec_type: str,
    domain_policy_id: str,
    coordinates: dict[str, str],
    harvested: datetime = RECENT,
    tags: list[str] | None = None,
) -> None:
    row: dict[str, object] = {
        "record_id": record_id,
        "type": rec_type,
        "domain_policy_id": domain_policy_id,
        "coordinates": coordinates,
        "harvested_at": harvested,
    }
    if tags is not None:
        row["tags"] = tags
    records.put(row)


def test_map_snapshot_builds_pack_scoped_table() -> None:
    records, snapshots, morph = _stores()
    _put(
        records,
        "fin-paper",
        rec_type="paper",
        domain_policy_id="finance/1",
        coordinates=FINANCE_COORDS,
    )
    _put(
        records,
        "opt-paper",
        rec_type="paper",
        domain_policy_id="optimization/1",
        coordinates=OPT_COORDS,
    )
    snapshots.commit("snap", ["fin-paper", "opt-paper"], schema_version=1)
    morph.mark_inspected(
        archive_cell_key(domain_policy_id="finance/1", cell_id=FINANCE_CELL),
        AS_OF,
    )
    mapped = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    ).run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        snapshot_state="calibration",
        expected_cell_ids=frozenset({FINANCE_CELL}),
    )
    assert mapped["snapshot_id"] == "snap"
    assert mapped["domain_policy_id"] == "finance/1"
    table = mapped["cell_statuses"]
    assert len(table) == 336
    assert table[FINANCE_CELL] == "Code-gap"
    assert OPT_CELL not in table
    assert sum(status == "Unknown" for status in table.values()) == 335


def test_map_snapshot_honors_overridden_window_days() -> None:
    records, snapshots, morph = _stores()
    aged = AS_OF - timedelta(days=400)
    for index in range(3):
        _put(
            records,
            f"fin-paper-{index}",
            rec_type="paper",
            domain_policy_id="finance/1",
            coordinates=FINANCE_COORDS,
            harvested=aged,
        )
    _put(
        records,
        "fin-code",
        rec_type="code",
        domain_policy_id="finance/1",
        coordinates=FINANCE_COORDS,
        harvested=aged,
    )
    assert (
        snapshots.commit(
            "snap",
            ["fin-paper-0", "fin-paper-1", "fin-paper-2", "fin-code"],
            schema_version=1,
        )
        == 1
    )
    mapper = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    )
    defaulted = mapper.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        snapshot_state="calibration",
        expected_cell_ids=frozenset({FINANCE_CELL}),
    )
    shortened = mapper.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        snapshot_state="calibration",
        expected_cell_ids=frozenset({FINANCE_CELL}),
        window_days=365,
    )
    assert defaulted["window_days"] == 730
    assert shortened["window_days"] == 365
    assert defaulted["cell_statuses"][FINANCE_CELL] == "Active"
    assert shortened["cell_statuses"][FINANCE_CELL] == "Unknown"


def test_map_snapshot_isolates_optimization_pack() -> None:
    records, snapshots, morph = _stores()
    _put(
        records,
        "fin-paper",
        rec_type="paper",
        domain_policy_id="finance/1",
        coordinates=FINANCE_COORDS,
    )
    _put(
        records,
        "opt-paper",
        rec_type="paper",
        domain_policy_id="optimization/1",
        coordinates=OPT_COORDS,
    )
    snapshots.commit("snap", ["fin-paper", "opt-paper"], schema_version=1)
    mapped = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    ).run(
        snapshot_id="snap",
        domain_policy_id="optimization/1",
        snapshot_state="calibration",
        expected_cell_ids=frozenset({OPT_CELL}),
    )
    table = mapped["cell_statuses"]
    assert len(table) == 8
    assert table[OPT_CELL] == "Code-gap"
    assert FINANCE_CELL not in table
    assert sum(status == "Unknown" for status in table.values()) == 7


def test_expected_cells_do_not_leak_across_packs() -> None:
    records, snapshots, morph = _stores()
    snapshots.commit("snap", [], schema_version=1)
    morph.mark_inspected(
        archive_cell_key(domain_policy_id="finance/1", cell_id=FINANCE_CELL),
        AS_OF,
    )
    finance = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    ).run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        snapshot_state="calibration",
        expected_cell_ids=frozenset({FINANCE_CELL}),
    )
    optimization = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    ).run(
        snapshot_id="snap",
        domain_policy_id="optimization/1",
        snapshot_state="calibration",
        expected_cell_ids=frozenset({OPT_CELL}),
    )
    assert finance["cell_statuses"][FINANCE_CELL] == "Missing"
    assert OPT_CELL not in finance["cell_statuses"]
    assert optimization["cell_statuses"][OPT_CELL] == "Missing"
    assert FINANCE_CELL not in optimization["cell_statuses"]


def test_map_rejects_unknown_snapshot_and_policy() -> None:
    records, snapshots, morph = _stores()
    use_case = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    )
    with pytest.raises(ValueError, match="unknown snapshot_id"):
        use_case.run(
            snapshot_id="missing",
            domain_policy_id="finance/1",
            snapshot_state="calibration",
        )
    snapshots.commit("snap", [], schema_version=1)
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        use_case.run(snapshot_id="snap", domain_policy_id="", snapshot_state="calibration")
    with pytest.raises(UnknownDomainPolicy, match="unknown domain_policy_id"):
        use_case.run(
            snapshot_id="snap",
            domain_policy_id="missing/1",
            snapshot_state="calibration",
        )


def test_rank_guard_consumes_mapped_statuses() -> None:
    records, snapshots, morph = _stores()
    snapshots.commit("snap", [], schema_version=1)
    mapped = MapSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        morph=morph,
        clock=FixedClock(AS_OF),
    ).run(
        snapshot_id="snap",
        domain_policy_id="optimization/1",
        snapshot_state="calibration",
    )
    with pytest.raises(RankGuardBlocked, match="rank_guard_blocked"):
        RankArchiveUseCase(
            cell_statuses=mapped["cell_statuses"],
            domain_policy_id="optimization/1",
        ).run(elite_cell_ids=set())


def test_map_handler_and_runner_persist_and_dispatch_map_job(tmp_path: Path) -> None:
    container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
    )
    records = container.ctx.records
    snapshots = container.ctx.snapshots
    morph = container.ctx.morph
    records.put(
        {
            "record_id": "fin-paper",
            "type": "paper",
            "domain_policy_id": "finance/1",
            "coordinates": FINANCE_COORDS,
            "harvested_at": RECENT.isoformat(),
            "content_hash": "fin-paper",
            "paraphrase": "p",
            "source": "s",
        }
    )
    assert snapshots.commit("snap", ["fin-paper"], schema_version=1) == 1
    morph.mark_inspected(
        archive_cell_key(domain_policy_id="finance/1", cell_id=FINANCE_CELL),
        AS_OF,
    )

    result = run_job(
        container,
        "map",
        {
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "snapshot_state": "calibration",
            "expected_cell_ids": [FINANCE_CELL],
        },
        AS_OF,
    )

    assert result["status"] == "succeeded"
    assert result["snapshot_id"] == "snap"
    assert result["domain_policy_id"] == "finance/1"
    assert result["cell_statuses"][FINANCE_CELL] == "Code-gap"
    job_row = container.database.fetchone(
        "SELECT status, payload_json FROM nsqd_jobs WHERE type = 'map'"
    )
    assert job_row is not None
    assert job_row["status"] == "succeeded"
    assert FINANCE_CELL in str(job_row["payload_json"])


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"domain_policy_id": "finance/1", "snapshot_state": "calibration"},
            "snapshot_id is required",
        ),
        ({"snapshot_id": "snap", "snapshot_state": "calibration"}, "domain_policy_id is required"),
        ({"snapshot_id": "snap", "domain_policy_id": "finance/1"}, "snapshot_state is required"),
        (
            {
                "snapshot_id": "snap",
                "domain_policy_id": "finance/1",
                "snapshot_state": "calibration",
                "expected_cell_ids": "not-a-list",
            },
            "expected_cell_ids must be a list of strings",
        ),
        (
            {
                "snapshot_id": "snap",
                "domain_policy_id": "finance/1",
                "snapshot_state": "calibration",
                "expected_cell_ids": [FINANCE_CELL, 7],
            },
            "expected_cell_ids must be a list of strings",
        ),
        (
            {
                "snapshot_id": "snap",
                "domain_policy_id": "finance/1",
                "snapshot_state": "calibration",
                "window_days": 0,
            },
            "window_days must be a positive int",
        ),
    ],
)
def test_map_runner_rejects_malformed_payload(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    container = build_container(
        db_path=tmp_path / "bad-map.sqlite",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
    )
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    with pytest.raises(ValueError, match=message):
        run_job(container, "map", payload, AS_OF)

    job_row = container.database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs ORDER BY created_at DESC LIMIT 1"
    )
    assert job_row is not None
    assert job_row["status"] == "failed"
