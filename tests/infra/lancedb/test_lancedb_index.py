from __future__ import annotations

from pathlib import Path

import pytest

from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex


def test_lancedb_roundtrip(tmp_path: Path) -> None:
    lancedb = pytest.importorskip("lancedb")
    has_connect = (
        hasattr(lancedb, "connect")
        or hasattr(lancedb, "lancedb_connect")
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "connect"))
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "lancedb_connect"))
    )
    if not has_connect:
        pytest.skip("lancedb connect API not available")
    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.upsert("paper", [0.1, 0.2, 0.3])
    results = index.query([0.1, 0.2, 0.3], limit=1)
    assert results
    assert results[0][0] == "paper"


def test_lancedb_upsert_replaces_existing_paper_embedding(tmp_path: Path) -> None:
    lancedb = pytest.importorskip("lancedb")
    if not hasattr(lancedb, "connect"):
        pytest.skip("lancedb connect API not available")
    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.upsert("paper", [0.1, 0.2, 0.3])
    index.upsert("paper", [0.3, 0.2, 0.1])

    results = index.query([0.3, 0.2, 0.1], limit=10)

    assert [paper_id for paper_id, _score in results].count("paper") == 1


def test_lancedb_query_scopes_ids_with_sql_punctuation(tmp_path: Path) -> None:
    lancedb = pytest.importorskip("lancedb")
    if not hasattr(lancedb, "connect"):
        pytest.skip("lancedb connect API not available")
    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    paper_id = "paper'quoted,comma"
    index.upsert(paper_id, [0.1, 0.2, 0.3])
    index.upsert("other", [0.1, 0.2, 0.3])

    results = index.query([0.1, 0.2, 0.3], limit=10, allowed_ids={paper_id})

    assert [result_id for result_id, _score in results] == [paper_id]


def test_lancedb_query_nonexistent_table_returns_empty(tmp_path: Path) -> None:
    lancedb = pytest.importorskip("lancedb")
    has_connect = (
        hasattr(lancedb, "connect")
        or hasattr(lancedb, "lancedb_connect")
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "connect"))
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "lancedb_connect"))
    )
    if not has_connect:
        pytest.skip("lancedb connect API not available")
    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    # Querying a nonexistent table returns an empty list (graceful fallback)
    results = index.query([0.1, 0.2, 0.3], limit=1)
    assert results == []
