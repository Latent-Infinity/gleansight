from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nsqd.null_adapters import (
    FixedClock,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullFrontierCardStore,
    NullMorphospaceStore,
    NullNsqdCandidateStore,
    NullNsqdJobQueue,
    SystemClock,
)
from nsqd.ports import Clock, CorpusHit, CorpusIndex, NsqdJobQueue


def test_clock_is_injected_and_fixed_clock_is_stable() -> None:
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    clock: Clock = FixedClock(as_of)
    assert clock.now() == as_of
    assert clock.now() == as_of
    system = SystemClock()
    now = system.now()
    assert now.tzinfo is UTC


def test_corpus_index_filters_by_snapshot_and_breaks_distance_ties() -> None:
    index: CorpusIndex = NullCorpusIndex()
    index.upsert("snap-a", "rec-b", [1.0, 0.0])
    index.upsert("snap-a", "rec-a", [1.0, 0.0])
    index.upsert("snap-b", "rec-c", [0.0, 1.0])
    hits = index.query("snap-a", [1.0, 0.0], k=5)
    assert [hit.record_id for hit in hits] == ["rec-a", "rec-b"]
    assert all(isinstance(hit, CorpusHit) for hit in hits)
    assert hits[0].rank == 1
    assert [hit.record_id for hit in index.query("snap-b", [0.0, 1.0], k=5)] == ["rec-c"]
    assert index.query("snap-missing", [1.0, 0.0], k=5) == []


def test_job_claim_is_exclusive_and_cancel_prevents_claim() -> None:
    queue: NsqdJobQueue = NullNsqdJobQueue()
    clock = FixedClock(datetime(2024, 1, 1, tzinfo=UTC))
    job_id = queue.enqueue("diverge", {"axiom": "x"}, run_after=None)
    first = queue.claim_next(clock.now())
    second = queue.claim_next(clock.now())
    assert first is not None
    assert first.job_id == job_id
    assert first.status == "running"
    assert second is None
    queue.mark_succeeded(job_id)
    later = queue.enqueue("ground", {}, run_after=clock.now() + timedelta(hours=1))
    assert queue.claim_next(clock.now()) is None
    claimed_later = queue.claim_next(clock.now() + timedelta(hours=1))
    assert claimed_later is not None
    assert claimed_later.job_id == later
    cancel_id = queue.enqueue("score", {})
    queue.cancel(cancel_id)
    assert queue.claim_next(clock.now() + timedelta(hours=1)) is None


def test_corpus_and_snapshot_missing_rows_and_list_ids() -> None:
    records = NullCorpusRecordStore()
    records.put({"record_id": "r2", "paraphrase": "b"})
    records.put({"record_id": "r1", "paraphrase": "a"})
    assert records.list_ids() == ["r1", "r2"]
    assert records.get("missing") is None
    snapshots = NullCorpusSnapshotStore()
    assert snapshots.get("missing") is None
    assert snapshots.record_ids("missing") == []
    snapshots.commit("snap", ["r1"], schema_version=1)
    assert snapshots.get("snap") == {
        "snapshot_id": "snap",
        "record_ids": ["r1"],
        "schema_version": 1,
        "corpus_version": 1,
    }
    morph = NullMorphospaceStore()
    assert morph.get_cell("missing") is None


def test_frontier_elite_clear_and_missing_cell() -> None:
    cards = NullFrontierCardStore()
    cards.put_card({"card_id": "c1", "cell_id": "cell"})
    assert cards.get_card("missing") is None
    assert cards.elite_for_cell("cell") is None
    cards.set_elite("cell", "c1")
    assert cards.elite_for_cell("cell") == {"card_id": "c1", "cell_id": "cell"}
    cards.set_elite("cell", None)
    assert cards.elite_for_cell("cell") is None


def test_job_retry_fail_and_attempt_cap() -> None:
    queue: NsqdJobQueue = NullNsqdJobQueue(max_attempts=2)
    now = datetime(2024, 1, 1, tzinfo=UTC)
    later = now + timedelta(minutes=5)
    job_id = queue.enqueue("ground", {"n": 1})
    first = queue.claim_next(now)
    assert first is not None
    queue.mark_retryable(job_id, "tmp", later)
    assert queue.claim_next(now) is None
    retry = queue.claim_next(later)
    assert retry is not None
    assert retry.attempts == 2
    queue.mark_retryable(job_id, "tmp-2", later)
    assert queue.claim_next(later) is None
    fail_id = queue.enqueue("score", {})
    claimed = queue.claim_next(later)
    assert claimed is not None
    assert claimed.job_id == fail_id
    queue.mark_failed(fail_id, "boom")
    assert queue.claim_next(later) is None


def test_null_queue_claims_specific_job_without_touching_older_work() -> None:
    queue: NsqdJobQueue = NullNsqdJobQueue()
    now = datetime(2024, 1, 1, tzinfo=UTC)
    older = queue.enqueue("harvest", {"older": True})
    target = queue.enqueue("diverge", {"target": True})

    claimed = queue.claim_job(target, now)

    assert claimed is not None
    assert claimed.job_id == target
    next_job = queue.claim_next(now)
    assert next_job is not None
    assert next_job.job_id == older


def test_index_zero_vector_distance_is_one() -> None:
    index = NullCorpusIndex()
    index.upsert("snap", "rec-zero", [0.0, 0.0])
    index.upsert("snap", "rec-unit", [1.0, 0.0])
    hits = index.query("snap", [0.0, 0.0], k=2)
    by_id = {hit.record_id: hit.distance for hit in hits}
    assert by_id["rec-zero"] == 1.0
    assert by_id["rec-unit"] == 1.0


def test_candidate_and_card_stores_round_trip() -> None:
    candidates = NullNsqdCandidateStore()
    candidates.put_artifact("abc", {"claim": "x"})
    assert candidates.get_artifact("abc") == {"claim": "x"}
    assert candidates.get_artifact("missing") is None
    cards = NullFrontierCardStore()
    cards.put_card({"card_id": "c1", "cell_id": "cell"})
    cards.set_elite("cell", "c1")
    assert cards.elite_for_cell("cell") == {"card_id": "c1", "cell_id": "cell"}
    records = NullCorpusRecordStore()
    records.put({"record_id": "r1", "paraphrase": "p"})
    assert records.get("r1") is not None
    snapshots = NullCorpusSnapshotStore()
    snapshots.commit("snap", ["r1"], schema_version=1)
    assert snapshots.record_ids("snap") == ["r1"]
    morph = NullMorphospaceStore()
    morph.mark_inspected("cell", datetime(2024, 1, 1, tzinfo=UTC))
    assert morph.get_cell("cell") is not None


def test_null_adapters_deep_copy_nested_mutables_on_put_and_get() -> None:
    record = {"record_id": "r1", "meta": {"tags": ["a"]}}
    records = NullCorpusRecordStore()
    records.put(record)
    record["meta"]["tags"].append("source-mutation")
    stored_record = records.get("r1")
    assert stored_record == {"record_id": "r1", "meta": {"tags": ["a"]}}
    assert stored_record is not None
    stored_record["meta"]["tags"].append("returned-mutation")
    assert records.get("r1") == {"record_id": "r1", "meta": {"tags": ["a"]}}

    snapshots = NullCorpusSnapshotStore()
    snapshot_ids = ["r1"]
    snapshots.commit("snap", snapshot_ids, schema_version=1)
    snapshot_ids.append("source-mutation")
    assert snapshots.get("snap") == {
        "snapshot_id": "snap",
        "record_ids": ["r1"],
        "schema_version": 1,
        "corpus_version": 1,
    }
    got_snapshot = snapshots.get("snap")
    assert got_snapshot is not None
    got_snapshot["record_ids"].append("returned-mutation")
    listed_ids = snapshots.record_ids("snap")
    listed_ids.append("returned-mutation")
    assert snapshots.record_ids("snap") == ["r1"]

    candidate_payload = {"candidate": {"nested": ["x"]}, "grounding": {"layers": [{"n": 1}]}}
    candidates = NullNsqdCandidateStore()
    candidates.put_artifact("abc", candidate_payload)
    candidate_payload["candidate"]["nested"].append("source-mutation")
    stored_candidate = candidates.get_artifact("abc")
    assert stored_candidate == {
        "candidate": {"nested": ["x"]},
        "grounding": {"layers": [{"n": 1}]},
    }
    assert stored_candidate is not None
    stored_candidate["candidate"]["nested"].append("returned-mutation")
    assert candidates.get_artifact("abc") == {
        "candidate": {"nested": ["x"]},
        "grounding": {"layers": [{"n": 1}]},
    }

    cards = NullFrontierCardStore()
    card = {"card_id": "c1", "cell_id": "cell", "scores": {"parts": [1]}}
    cards.put_card(card)
    card["scores"]["parts"].append(2)
    stored_card = cards.get_card("c1")
    assert stored_card == {"card_id": "c1", "cell_id": "cell", "scores": {"parts": [1]}}
    assert stored_card is not None
    stored_card["scores"]["parts"].append(3)
    assert cards.get_card("c1") == {"card_id": "c1", "cell_id": "cell", "scores": {"parts": [1]}}

    queue = NullNsqdJobQueue()
    payload = {"candidate": {"nested": ["x"]}}
    job_id = queue.enqueue("diverge", payload)
    payload["candidate"]["nested"].append("source-mutation")
    claimed = queue.claim_next(datetime(2024, 1, 1, tzinfo=UTC))
    assert claimed is not None
    assert claimed.job_id == job_id
    assert claimed.payload == {"candidate": {"nested": ["x"]}}
    claimed.payload["candidate"]["nested"].append("returned-mutation")
    queue.mark_retryable(job_id, "tmp", datetime(2024, 1, 1, 0, 1, tzinfo=UTC))
    retried = queue.claim_next(datetime(2024, 1, 1, 0, 1, tzinfo=UTC))
    assert retried is not None
    assert retried.payload == {"candidate": {"nested": ["x"]}}


def test_job_queue_rejects_invalid_job_type_strings() -> None:
    queue = NullNsqdJobQueue()

    with pytest.raises(ValueError, match="unknown job type"):
        queue.enqueue("invalid", {})


def test_utc_boundaries_reject_naive_and_nonzero_offset_datetimes() -> None:
    naive = datetime(2024, 1, 1)
    plus_one = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    utc_now = datetime(2024, 1, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="UTC datetime"):
        FixedClock(naive)
    with pytest.raises(ValueError, match="UTC datetime"):
        FixedClock(plus_one)
    assert FixedClock(utc_now).now() == utc_now

    morph = NullMorphospaceStore()
    with pytest.raises(ValueError, match="UTC datetime"):
        morph.mark_inspected("cell", naive)
    with pytest.raises(ValueError, match="UTC datetime"):
        morph.mark_inspected("cell", plus_one)
    morph.mark_inspected("cell", utc_now)
    cell = morph.get_cell("cell")
    assert cell is not None
    assert cell["inspected_at"] == utc_now

    queue = NullNsqdJobQueue()
    with pytest.raises(ValueError, match="UTC datetime"):
        queue.enqueue("diverge", {}, run_after=naive)
    with pytest.raises(ValueError, match="UTC datetime"):
        queue.enqueue("diverge", {}, run_after=plus_one)
    job_id = queue.enqueue("diverge", {}, run_after=utc_now)
    with pytest.raises(ValueError, match="UTC datetime"):
        queue.claim_next(naive)
    with pytest.raises(ValueError, match="UTC datetime"):
        queue.claim_next(plus_one)
    claimed = queue.claim_next(utc_now)
    assert claimed is not None
    assert claimed.job_id == job_id
    with pytest.raises(ValueError, match="UTC datetime"):
        queue.mark_retryable(job_id, "tmp", naive)
    with pytest.raises(ValueError, match="UTC datetime"):
        queue.mark_retryable(job_id, "tmp", plus_one)
    queue.mark_retryable(job_id, "tmp", utc_now + timedelta(minutes=1))
