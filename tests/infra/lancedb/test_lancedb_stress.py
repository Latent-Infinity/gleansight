from __future__ import annotations

from pathlib import Path

import pytest

from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex

pytestmark = pytest.mark.integration


def test_lancedb_handles_large_embeddings(tmp_path: Path) -> None:
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
    embedding = [0.001] * 1024
    index.upsert("paper", embedding)
    results = index.query(embedding, limit=1)
    assert results
    assert results[0][0] == "paper"
