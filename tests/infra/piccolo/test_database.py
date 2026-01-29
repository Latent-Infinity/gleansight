from __future__ import annotations

from pathlib import Path

import pytest
from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

from papers.infra.piccolo.database import PiccoloDatabase


def test_execute_and_fetch(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.execute("CREATE TABLE test (id TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO test (id, value) VALUES (?, ?)", ["a", "b"])
    row = db.fetchone("SELECT * FROM test WHERE id = ?", ["a"])
    assert row is not None
    assert row["value"] == "b"
    rows = db.fetchall("SELECT * FROM test")
    assert len(rows) == 1


def test_transaction_rolls_back(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.execute("CREATE TABLE test (id TEXT PRIMARY KEY)")

    async def _tx() -> None:
        async with db.engine.transaction():
            await db.engine.run_querystring(QueryString("INSERT INTO test (id) VALUES ('a')"))
            await db.engine.run_querystring(QueryString("INSERT INTO test (id) VALUES ('a')"))

    with pytest.raises(Exception):
        run_sync(_tx())
    rows = db.fetchall("SELECT * FROM test")
    assert rows == []
