from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloPaperProjectStore,
    PiccoloPaperTagStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)


def _setup_db(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "taxonomy.sqlite")
    db.initialize_schema()


def test_tag_store_create_and_get(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloTagStore()
    store.create_tag("tag-1", "methods", "method")

    tag = store.get("tag-1")
    assert tag is not None
    assert tag["name"] == "methods"
    assert tag["type"] == "method"


def test_tag_store_get_by_name(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloTagStore()
    store.create_tag("tag-1", "methods", "method")

    tag = store.get_by_name("methods")
    assert tag is not None
    assert tag["tag_id"] == "tag-1"


def test_tag_store_missing_returns_none(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloTagStore()

    assert store.get("missing") is None
    assert store.get_by_name("missing") is None


def test_project_store_create_and_get(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloProjectStore()
    store.create_project("proj-1", "Project", "Desc")

    project = store.get("proj-1")
    assert project is not None
    assert project["name"] == "Project"
    assert project["description"] == "Desc"


def test_project_store_get_by_name(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloProjectStore()
    store.create_project("proj-1", "Project", None)

    project = store.get_by_name("Project")
    assert project is not None
    assert project["project_id"] == "proj-1"


def test_project_store_missing_returns_none(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloProjectStore()

    assert store.get("missing") is None
    assert store.get_by_name("missing") is None


def test_paper_tag_store_attach_and_check(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloPaperTagStore()

    assert store.is_attached("paper-1", "tag-1") is False
    store.attach("paper-1", "tag-1", confidence=0.75)
    assert store.is_attached("paper-1", "tag-1") is True


def test_paper_tag_store_distinct_pairs(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloPaperTagStore()

    store.attach("paper-1", "tag-1")
    assert store.is_attached("paper-1", "tag-1") is True
    assert store.is_attached("paper-1", "tag-2") is False
    assert store.is_attached("paper-2", "tag-1") is False


def test_paper_project_store_attach_and_check(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloPaperProjectStore()

    assert store.is_attached("paper-1", "proj-1") is False
    store.attach("paper-1", "proj-1", label="seed")
    assert store.is_attached("paper-1", "proj-1") is True


def test_paper_project_store_list_papers(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloPaperProjectStore()

    store.attach("paper-1", "proj-1", label="seed")
    store.attach("paper-2", "proj-1", label="seed")
    store.attach("paper-3", "proj-1", label="secondary")

    papers = store.list_paper_ids("proj-1")
    assert set(papers) == {"paper-1", "paper-2", "paper-3"}


def test_paper_project_store_list_papers_with_label(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloPaperProjectStore()

    store.attach("paper-1", "proj-1", label="seed")
    store.attach("paper-2", "proj-1", label="secondary")

    papers = store.list_paper_ids("proj-1", label="seed")
    assert papers == ["paper-1"]


def test_tag_store_custom_created_at(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloTagStore()
    now = datetime(2024, 1, 1, tzinfo=UTC)
    store.create_tag("tag-1", "methods", "method", created_at=now.isoformat())

    tag = store.get("tag-1")
    assert tag is not None
    assert "created_at" in tag


def test_project_store_custom_created_at(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = PiccoloProjectStore()
    now = datetime(2024, 1, 1, tzinfo=UTC)
    store.create_project("proj-1", "Project", None, created_at=now.isoformat())

    project = store.get("proj-1")
    assert project is not None
    assert "created_at" in project
