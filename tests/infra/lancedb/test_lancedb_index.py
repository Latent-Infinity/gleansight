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
    results = index.query([0.1, 0.2, 0.3], limit=1)
    assert results == []


def test_lancedb_contract_specific_tables_isolate_embedding_families(tmp_path: Path) -> None:
    lancedb = pytest.importorskip("lancedb")
    has_connect = (
        hasattr(lancedb, "connect")
        or hasattr(lancedb, "lancedb_connect")
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "connect"))
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "lancedb_connect"))
    )
    if not has_connect:
        pytest.skip("lancedb connect API not available")
    qwen = LanceDBVectorIndex(
        LanceDBConfig(
            path=tmp_path, embedding_model="qwen3-embedding:latest", embedding_dimension=3
        )
    )
    legacy = LanceDBVectorIndex(
        LanceDBConfig(path=tmp_path, embedding_model="test-only-sha256:v1", embedding_dimension=3)
    )

    qwen.upsert("paper-qwen", [0.1, 0.2, 0.3])
    legacy.upsert("paper-legacy", [0.1, 0.2, 0.3])

    assert [paper_id for paper_id, _score in qwen.query([0.1, 0.2, 0.3], limit=10)] == [
        "paper-qwen"
    ]
    assert [paper_id for paper_id, _score in legacy.query([0.1, 0.2, 0.3], limit=10)] == [
        "paper-legacy"
    ]


def test_lancedb_contract_dimension_mismatch_requires_rebuild_guidance(tmp_path: Path) -> None:
    lancedb = pytest.importorskip("lancedb")
    has_connect = (
        hasattr(lancedb, "connect")
        or hasattr(lancedb, "lancedb_connect")
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "connect"))
        or (hasattr(lancedb, "db") and hasattr(lancedb.db, "lancedb_connect"))
    )
    if not has_connect:
        pytest.skip("lancedb connect API not available")
    index = LanceDBVectorIndex(
        LanceDBConfig(
            path=tmp_path, embedding_model="qwen3-embedding:latest", embedding_dimension=3
        )
    )

    with pytest.raises(ValueError, match="rebuild"):
        index.query([0.1, 0.2], limit=1)
