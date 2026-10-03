from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from papers.infra.piccolo.database import PiccoloDatabase
from research.catalog.models import CatalogError
from research.catalog.service import ResearchCatalog
from research.catalog.store import CatalogStore
from tests.research.test_capacity_verification import verified_fixture as verified_fixture


def service(root: Path) -> ResearchCatalog:
    return ResearchCatalog(
        CatalogStore(PiccoloDatabase(root / "data/papers.sqlite", bind_on_init=False)), root
    )


def owned_pair(root: Path, source: Path) -> tuple[Path, Path]:
    paths = root / "output/capacity/a", root / "output/capacity/b"
    for path in paths:
        shutil.copytree(source, path)
    return paths


def test_lazy_database_pagination_and_parameterized_unknown_identity(tmp_path: Path) -> None:
    store = service(tmp_path).store
    assert store.list() == () and not store.database.path.exists()
    with pytest.raises(CatalogError, match="not indexed"):
        store.get("' OR 1=1 --")
    with pytest.raises(CatalogError, match="pagination"):
        store.list(limit=101)
    store.database.path.parent.mkdir()
    with sqlite3.connect(store.database.path) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER)")
    assert store.list() == ()
    with pytest.raises(CatalogError, match="not indexed"):
        store.get("a" * 64)


def test_portable_restart_immutable_identity_and_stale_reverification(
    verified_fixture: Path, tmp_path: Path
) -> None:
    root = tmp_path / "original"
    first, second = owned_pair(root, verified_fixture)
    api = service(root)
    indexed = api.index(first)
    other = api.index(second)
    assert indexed.record is not None
    with sqlite3.connect(api.store.database.path) as connection:
        before = connection.execute(
            "SELECT document_json FROM research_run_catalog WHERE run_id=?", (indexed.run_id,)
        ).fetchone()[0]
    api.store.put(indexed.bundle_path, indexed.record)
    with pytest.raises(CatalogError, match="identity"):
        api.store.put(
            indexed.bundle_path, indexed.record.model_copy(update={"code_sha256": "e" * 64})
        )
    for ids in ((indexed.run_id,), (indexed.run_id, indexed.run_id)):
        with pytest.raises(CatalogError, match="distinct"):
            api.compare(ids)
    restored = tmp_path / "restored"
    shutil.copytree(root, restored)
    current = service(restored)
    assert current.compare((indexed.run_id, other.run_id)).comparable
    assert len(current.list(limit=1, offset=1)) == 1
    with sqlite3.connect(current.store.database.path) as connection:
        assert (
            before
            == connection.execute(
                "SELECT document_json FROM research_run_catalog WHERE run_id=?", (indexed.run_id,)
            ).fetchone()[0]
        )
        tampered = json.loads(before)
        tampered["code_sha256"] = "e" * 64
        connection.execute(
            "UPDATE research_run_catalog SET document_json=? WHERE run_id=?",
            (json.dumps(tampered), indexed.run_id),
        )
    stale = next(item for item in current.list() if item.run_id == indexed.run_id)
    assert not stale.verified and stale.record is None
    with pytest.raises(CatalogError, match="identity"):
        current.compare((indexed.run_id, other.run_id))


def test_only_owned_unsymlinked_bundles_are_selected(
    verified_fixture: Path, tmp_path: Path
) -> None:
    api = service(tmp_path)
    with pytest.raises(CatalogError, match="output"):
        api.verify(verified_fixture)
    path = tmp_path / "output/link"
    path.parent.mkdir()
    path.symlink_to(verified_fixture, target_is_directory=True)
    with pytest.raises(CatalogError, match="output"):
        api.verify(path)
