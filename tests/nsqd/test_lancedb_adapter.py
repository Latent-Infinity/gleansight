from __future__ import annotations

from pathlib import Path

import pytest

from nsqd.infra.lancedb.index import LanceDBCorpusIndex
from nsqd.ports import CorpusHit


def test_lancedb_corpus_index_filters_snapshot_and_breaks_ties(tmp_path: Path) -> None:
    pytest.importorskip("lancedb")
    index = LanceDBCorpusIndex(tmp_path / "corpus.lancedb")
    index.upsert("snap-a", "rec-b", [1.0, 0.0])
    index.upsert("snap-a", "rec-a", [1.0, 0.0])
    index.upsert("snap-b", "rec-c", [0.0, 1.0])
    hits = index.query("snap-a", [1.0, 0.0], k=5)
    assert [hit.record_id for hit in hits] == ["rec-a", "rec-b"]
    assert all(isinstance(hit, CorpusHit) for hit in hits)
    assert hits[0].rank == 1
    assert hits[0].distance == pytest.approx(0.0)
    assert [hit.record_id for hit in index.query("snap-b", [0.0, 1.0], k=5)] == ["rec-c"]
    filtered = index.query(
        "snap-a",
        [1.0, 0.0],
        k=5,
        allowed_record_ids=frozenset({"rec-b"}),
    )
    assert [hit.record_id for hit in filtered] == ["rec-b"]
    assert index.query("snap-missing", [1.0, 0.0], k=5) == []
    assert index.query("snap-a", [1.0, 0.0], k=0) == []
    empty = LanceDBCorpusIndex(tmp_path / "empty.lancedb")
    assert empty.query("snap-a", [1.0, 0.0], k=5) == []


def test_lancedb_corpus_index_uses_unambiguous_snapshot_record_keys(tmp_path: Path) -> None:
    pytest.importorskip("lancedb")
    index = LanceDBCorpusIndex(tmp_path / "corpus.lancedb")
    index.upsert("a:b", "c", [1.0, 0.0])
    index.upsert("a", "b:c", [0.0, 1.0])

    left_hits = index.query("a:b", [1.0, 0.0], k=5)
    right_hits = index.query("a", [0.0, 1.0], k=5)

    assert [hit.record_id for hit in left_hits] == ["c"]
    assert [hit.record_id for hit in right_hits] == ["b:c"]


@pytest.mark.integration
def test_lancedb_corpus_index_orders_large_ties_deterministically(tmp_path: Path) -> None:
    pytest.importorskip("lancedb")
    index = LanceDBCorpusIndex(tmp_path / "corpus.lancedb")
    for i in range(60):
        index.upsert("snap-target", f"rec-{i:02d}", [1.0, 0.0])
        index.upsert("snap-other", f"other-{i:02d}", [1.0, 0.0])

    hits = index.query("snap-target", [1.0, 0.0], k=5)

    assert [hit.record_id for hit in hits] == [
        "rec-00",
        "rec-01",
        "rec-02",
        "rec-03",
        "rec-04",
    ]
