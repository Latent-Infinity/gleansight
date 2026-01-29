from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, cast

from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex


class _FakeSearch:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._limit = len(rows)

    def limit(self, limit: int) -> _FakeSearch:
        self._limit = limit
        return self

    def to_list(self) -> list[dict[str, object]]:
        return self._rows[: self._limit]


class _FakeTable:
    def __init__(self) -> None:
        self._rows: list[dict[str, object]] = []

    def add(self, rows: list[dict[str, object]]) -> None:
        self._rows.extend(rows)

    def search(self, _embedding: list[float], *, vector_column_name: str) -> _FakeSearch:
        rows = [
            {"paper_id": row["paper_id"], "_distance": 0.0}
            for row in self._rows
            if vector_column_name
        ]
        return _FakeSearch(rows)


class _FakeDB:
    def __init__(self) -> None:
        self._table: _FakeTable | None = None

    def open_table(self, _name: str) -> _FakeTable:
        if self._table is None:
            raise RuntimeError("missing table")
        return self._table

    def create_table(self, _name: str, *, schema: object) -> _FakeTable:
        _ = schema
        self._table = _FakeTable()
        return self._table


def test_lancedb_index_with_fake_modules(tmp_path: Path, monkeypatch) -> None:
    fake_db = _FakeDB()
    fake_lancedb = types.ModuleType("lancedb")
    fake_lancedb_any = cast(Any, fake_lancedb)
    fake_lancedb_any.connect = lambda _path: fake_db
    fake_lancedb_any.vector = lambda dimension: f"vector({dimension})"

    fake_numpy = types.ModuleType("numpy")
    fake_numpy_any = cast(Any, fake_numpy)
    fake_numpy_any.array = lambda values, dtype=None: list(values)

    fake_pyarrow = types.ModuleType("pyarrow")
    fake_pyarrow_any = cast(Any, fake_pyarrow)
    fake_pyarrow_any.schema = lambda fields: fields
    fake_pyarrow_any.string = lambda: "string"

    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)

    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.upsert("paper-1", [0.1, 0.2, 0.3])
    results = index.query([0.1, 0.2, 0.3], limit=1)

    assert results
    assert results[0][0] == "paper-1"


def test_lancedb_index_with_lancedb_connect(tmp_path: Path, monkeypatch) -> None:
    """Test connection via lancedb.lancedb_connect method."""
    fake_db = _FakeDB()
    fake_lancedb = types.ModuleType("lancedb")
    fake_lancedb_any = cast(Any, fake_lancedb)
    # Only provide lancedb_connect (no connect)
    fake_lancedb_any.lancedb_connect = lambda _path: fake_db
    fake_lancedb_any.vector = lambda dimension: f"vector({dimension})"

    fake_numpy = types.ModuleType("numpy")
    fake_numpy_any = cast(Any, fake_numpy)
    fake_numpy_any.array = lambda values, dtype=None: list(values)

    fake_pyarrow = types.ModuleType("pyarrow")
    fake_pyarrow_any = cast(Any, fake_pyarrow)
    fake_pyarrow_any.schema = lambda fields: fields
    fake_pyarrow_any.string = lambda: "string"

    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)

    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.upsert("paper-2", [0.1, 0.2])
    results = index.query([0.1, 0.2], limit=1)

    assert results
    assert results[0][0] == "paper-2"


def test_lancedb_index_with_db_connect(tmp_path: Path, monkeypatch) -> None:
    """Test connection via lancedb.db.connect method."""
    fake_db = _FakeDB()
    fake_db_module = types.ModuleType("db")
    fake_db_module_any = cast(Any, fake_db_module)
    fake_db_module_any.connect = lambda _path: fake_db

    fake_lancedb = types.ModuleType("lancedb")
    fake_lancedb_any = cast(Any, fake_lancedb)
    fake_lancedb_any.db = fake_db_module
    fake_lancedb_any.vector = lambda dimension: f"vector({dimension})"

    fake_numpy = types.ModuleType("numpy")
    fake_numpy_any = cast(Any, fake_numpy)
    fake_numpy_any.array = lambda values, dtype=None: list(values)

    fake_pyarrow = types.ModuleType("pyarrow")
    fake_pyarrow_any = cast(Any, fake_pyarrow)
    fake_pyarrow_any.schema = lambda fields: fields
    fake_pyarrow_any.string = lambda: "string"

    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)

    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.upsert("paper-3", [0.1])
    results = index.query([0.1], limit=1)

    assert results
    assert results[0][0] == "paper-3"


def test_lancedb_index_with_db_lancedb_connect(tmp_path: Path, monkeypatch) -> None:
    """Test connection via lancedb.db.lancedb_connect method."""
    fake_db = _FakeDB()
    fake_db_module = types.ModuleType("db")
    fake_db_module_any = cast(Any, fake_db_module)
    fake_db_module_any.lancedb_connect = lambda _path: fake_db

    fake_lancedb = types.ModuleType("lancedb")
    fake_lancedb_any = cast(Any, fake_lancedb)
    fake_lancedb_any.db = fake_db_module
    fake_lancedb_any.vector = lambda dimension: f"vector({dimension})"

    fake_numpy = types.ModuleType("numpy")
    fake_numpy_any = cast(Any, fake_numpy)
    fake_numpy_any.array = lambda values, dtype=None: list(values)

    fake_pyarrow = types.ModuleType("pyarrow")
    fake_pyarrow_any = cast(Any, fake_pyarrow)
    fake_pyarrow_any.schema = lambda fields: fields
    fake_pyarrow_any.string = lambda: "string"

    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)

    index = LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
    index.upsert("paper-4", [0.5])
    results = index.query([0.5], limit=1)

    assert results
    assert results[0][0] == "paper-4"


def test_lancedb_index_no_supported_api_raises(tmp_path: Path, monkeypatch) -> None:
    """Test that missing connect API raises AttributeError."""
    import pytest

    fake_lancedb = types.ModuleType("lancedb")
    # Don't add any connect methods

    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)

    with pytest.raises(AttributeError, match="no supported connect API"):
        LanceDBVectorIndex(LanceDBConfig(path=tmp_path))
