from __future__ import annotations

from pathlib import Path

import pytest

from nsqd.infra.lancedb.index import LanceDBCorpusIndex
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


@pytest.mark.parametrize("corpus", [False, True])
@pytest.mark.parametrize("operation", ["query", "upsert"])
def test_corrupt_table_errors_propagate(tmp_path: Path, corpus: bool, operation: str) -> None:
    pytest.importorskip("lancedb")
    vector = [0.1, 0.2, 0.3]
    if corpus:
        index = LanceDBCorpusIndex(tmp_path)
        index.upsert("snapshot", "paper", vector)
    else:
        index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
        index.upsert("paper", vector)

    manifests = list(tmp_path.glob("*.lance/_versions/*.manifest"))
    assert manifests, "the real seeded table must have a persisted manifest"
    for manifest in manifests:
        manifest.write_bytes(b"corrupt")

    with pytest.raises(RuntimeError):
        if isinstance(index, LanceDBCorpusIndex):
            if operation == "query":
                index.query("snapshot", vector, k=1)
            else:
                index.upsert("snapshot", "another-paper", vector)
        elif operation == "query":
            index.query(vector, limit=1)
        else:
            index.upsert("another-paper", vector)


def test_reset_propagates_storage_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("lancedb")
    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))

    def fail_drop(*args: object, **kwargs: object) -> None:
        raise PermissionError("storage is read-only")

    monkeypatch.setattr(index._db, "drop_table", fail_drop)
    with pytest.raises(PermissionError, match="read-only"):
        index.reset()


def test_reset_of_absent_table_is_idempotent(tmp_path: Path) -> None:
    pytest.importorskip("lancedb")
    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.reset()
    index.reset()
    assert index.query([0.1, 0.2, 0.3], limit=1) == []
