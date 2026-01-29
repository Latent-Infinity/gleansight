from __future__ import annotations

from pathlib import Path

import pytest

from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex

pytestmark = pytest.mark.integration


def test_lancedb_real_roundtrip(tmp_path: Path) -> None:
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
