from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from nsqd.infra.piccolo.schema import NSQD_TABLE_NAMES
from nsqd.infra.piccolo.stores import (
    PiccoloCorpusRecordStore,
    PiccoloCorpusSnapshotStore,
    PiccoloFrontierCardStore,
    PiccoloMorphospaceStore,
    PiccoloNsqdCandidateStore,
    PiccoloNsqdJobQueue,
)
from nsqd.ports import NSQD_JOB_TYPES, NsqdJobType
from papers.infra.piccolo.database import _TABLES, PiccoloDatabase
from papers.infra.piccolo.migrations.runner import apply_forward_migrations
from papers.infra.piccolo.stores import PiccoloJobQueue


def _db(tmp_path: Path) -> PiccoloDatabase:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = PiccoloDatabase(tmp_path / "nsqd.sqlite")
    db.initialize_schema()
    return db


def test_nsqd_tables_are_not_created_by_paper_create_table_loop(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "pre.sqlite")
    for table in _TABLES:
        table.create_table(if_not_exists=True).run_sync()
    names = {
        str(row["name"])
        for row in db.fetchall("SELECT name FROM sqlite_schema WHERE type = 'table'")
    }
    assert "nsqd_jobs" not in names
    apply_forward_migrations(db)
    names = {
        str(row["name"])
        for row in db.fetchall("SELECT name FROM sqlite_schema WHERE type = 'table'")
    }
    assert set(NSQD_TABLE_NAMES) <= names
    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert "003_nsqd_tables" in versions


def test_initialize_schema_records_nsqd_migration(tmp_path: Path) -> None:
    db = _db(tmp_path)
    versions = {row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")}
    assert "003_nsqd_tables" in versions
    for name in NSQD_TABLE_NAMES:
        row = db.fetchone(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name = ?",
            [name],
        )
        assert row is not None


def test_nsqd_store_instances_remain_bound_to_original_database(tmp_path: Path) -> None:
    db1 = _db(tmp_path / "db1")
    db2 = _db(tmp_path / "db2")
    store1 = PiccoloCorpusRecordStore(db1)
    store1.put({"record_id": "db1-a", "paraphrase": "first"})

    store2 = PiccoloCorpusRecordStore(db2)
    store2.put({"record_id": "db2-a", "paraphrase": "second"})

    store1.put({"record_id": "db1-b", "paraphrase": "third"})

    assert store1.list_ids() == ["db1-a", "db1-b"]
    assert store2.list_ids() == ["db2-a"]
    assert (
        db1.fetchone(
            "SELECT record_id FROM nsqd_corpus_records WHERE record_id = ?",
            ["db1-b"],
        )
        is not None
    )
    assert (
        db2.fetchone(
            "SELECT record_id FROM nsqd_corpus_records WHERE record_id = ?",
            ["db1-b"],
        )
        is None
    )


@pytest.mark.parametrize("job_type", sorted(NSQD_JOB_TYPES))
def test_paper_jobs_reject_discovery_types(tmp_path: Path, job_type: str) -> None:
    db = _db(tmp_path)
    now = datetime.now(UTC).isoformat()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO jobs (
                job_id, type, status, paper_id, run_id, payload_json,
                attempts, max_attempts, run_after, last_error, created_at, updated_at
            ) VALUES (?, ?, 'queued', NULL, NULL, ?, 0, 3, NULL, NULL, ?, ?)
            """,
            [f"paper-{job_type}", job_type, "{}", now, now],
        )
    paper_queue = PiccoloJobQueue()
    with pytest.raises(sqlite3.IntegrityError):
        paper_queue.enqueue(job_type, None, None, {})


def test_nsqd_jobs_claim_retry_cancel_and_utc(tmp_path: Path) -> None:
    db = _db(tmp_path)
    queue = PiccoloNsqdJobQueue(db)
    now = datetime(2024, 1, 1, tzinfo=UTC)
    later = now + timedelta(hours=1)
    job_id = queue.enqueue("diverge", {"axiom": "x"}, run_after=None)
    first = queue.claim_next(now)
    second = queue.claim_next(now)
    assert first is not None
    assert first.job_id == job_id
    assert first.status == "running"
    assert first.type == "diverge"
    assert first.attempts == 1
    assert second is None
    queue.mark_retryable(job_id, "tmp", later)
    assert queue.claim_next(now) is None
    retried = queue.claim_next(later)
    assert retried is not None
    assert retried.attempts == 2
    queue.mark_failed(retried.job_id, "boom")
    assert queue.claim_next(later) is None

    cancel_id = queue.enqueue("ground", {})
    queue.cancel(cancel_id)
    assert queue.claim_next(later) is None

    ok_id = queue.enqueue("map", {"n": 1})
    claimed = queue.claim_next(later)
    assert claimed is not None
    assert claimed.job_id == ok_id
    queue.mark_succeeded(ok_id)
    assert queue.claim_next(later) is None

    invalid_job_type = cast(NsqdJobType, "analyze")
    with pytest.raises(ValueError, match="unknown job type"):
        queue.enqueue(invalid_job_type, {})
    with pytest.raises(ValueError, match="UTC"):
        queue.enqueue("harvest", {}, run_after=datetime(2024, 1, 1))


def test_nsqd_jobs_claim_specific_job_leaves_older_queued_job_untouched(tmp_path: Path) -> None:
    db = _db(tmp_path)
    queue = PiccoloNsqdJobQueue(db)
    now = datetime(2024, 1, 1, tzinfo=UTC)
    stale_job_id = queue.enqueue("harvest", {"seeded": True})
    target_job_id = queue.enqueue("diverge", {"axiom": "x"})

    claimed = queue.claim_job(target_job_id, now)

    assert claimed is not None
    assert claimed.job_id == target_job_id
    assert claimed.type == "diverge"
    stale_row = db.fetchone(
        "SELECT status, attempts FROM nsqd_jobs WHERE job_id = ?",
        [stale_job_id],
    )
    assert stale_row is not None
    assert stale_row["status"] == "queued"
    assert stale_row["attempts"] == 0


def test_piccolo_stores_round_trip(tmp_path: Path) -> None:
    db = _db(tmp_path)
    records = PiccoloCorpusRecordStore(db)
    records.put({"record_id": "r2", "paraphrase": "b"})
    records.put({"record_id": "r1", "paraphrase": "a"})
    records.put({"record_id": "r1", "paraphrase": "a"})
    with pytest.raises(ValueError, match="already committed"):
        records.put({"record_id": "r1", "paraphrase": "a2"})
    assert records.list_ids() == ["r1", "r2"]
    assert records.get("r1") == {"record_id": "r1", "paraphrase": "a"}
    assert records.get("missing") is None

    snapshots = PiccoloCorpusSnapshotStore(db)
    assert snapshots.commit("snap", ["r1", "r2"], schema_version=1) == 1
    assert snapshots.commit("snap", ["r1", "r2"], schema_version=1) == 1
    assert snapshots.commit("snap-2", ["r2"], schema_version=1) == 2
    with pytest.raises(
        ValueError,
        match="snapshot_id already committed with different content",
    ):
        snapshots.commit("snap", ["r1"], schema_version=2)
    assert snapshots.record_ids("snap") == ["r1", "r2"]
    snap = snapshots.get("snap")
    assert snap is not None
    assert snap["schema_version"] == 1
    assert snap["corpus_version"] == 1
    assert snapshots.get("missing") is None
    assert snapshots.record_ids("missing") == []

    candidates = PiccoloNsqdCandidateStore(db)
    with ThreadPoolExecutor(max_workers=2) as executor:
        inserted = list(
            executor.map(
                lambda payload: candidates.put_artifact_if_absent("race", payload),
                ({"claim": "first"}, {"claim": "second"}),
            )
        )
    assert sorted(inserted) == [False, True]
    assert candidates.get_artifact("race") in ({"claim": "first"}, {"claim": "second"})
    candidates.put_artifact("abc", {"claim": "x"})
    candidates.put_artifact(
        "abc",
        {"claim": "y", "axioms": [{"statement": "first"}, {"statement": "second"}]},
    )
    assert candidates.get_artifact("abc") == {
        "claim": "y",
        "axioms": [{"statement": "first"}, {"statement": "second"}],
    }
    assert candidates.get_artifact("missing") is None

    cards = PiccoloFrontierCardStore(db)
    cards.put_card({"card_id": "c1", "cell_id": "cell", "viability": 0})
    cards.put_card({"card_id": "c1", "cell_id": "cell", "viability": 1})
    assert cards.get_card("c1") == {"card_id": "c1", "cell_id": "cell", "viability": 1}
    assert cards.get_card("missing") is None
    assert cards.elite_for_cell("cell") is None
    cards.set_elite("cell", "c1")
    assert cards.elite_for_cell("cell") == {
        "card_id": "c1",
        "cell_id": "cell",
        "viability": 1,
    }
    cards.set_elite("cell", None)
    assert cards.elite_for_cell("cell") is None

    morph = PiccoloMorphospaceStore(db)
    inspected = datetime(2024, 1, 1, tzinfo=UTC)
    morph.mark_inspected("cell", inspected)
    later = datetime(2024, 2, 1, tzinfo=UTC)
    morph.mark_inspected("cell", later)
    row = morph.get_cell("cell")
    assert row is not None
    assert row["cell_id"] == "cell"
    assert row["inspected_at"] == later
    assert morph.get_cell("missing") is None
