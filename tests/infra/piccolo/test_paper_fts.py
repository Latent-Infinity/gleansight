from __future__ import annotations

from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import PiccoloPaperStore


def _setup(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "paperfts.sqlite")
    db.initialize_schema()


def test_search_matches_title(tmp_path: Path) -> None:
    _setup(tmp_path)
    store = PiccoloPaperStore()
    store.create_paper({"paper_id": "p1", "title": "Transformer Models"})
    store.create_paper({"paper_id": "p2", "title": "Other"})

    fts = PiccoloPaperFTS()
    results = fts.search("Transformer", limit=10)

    assert results == ["p1"]


def test_search_matches_abstract(tmp_path: Path) -> None:
    _setup(tmp_path)
    store = PiccoloPaperStore()
    store.create_paper({"paper_id": "p1", "title": "Title", "abstract": "deep learning"})

    fts = PiccoloPaperFTS()
    results = fts.search("learning", limit=10)

    assert results == ["p1"]


def test_search_matches_nonadjacent_literal_terms(tmp_path: Path) -> None:
    _setup(tmp_path)
    store = PiccoloPaperStore()
    store.create_paper({"paper_id": "p1", "title": "Deep methods for reliable learning"})

    assert PiccoloPaperFTS().search("deep learning", limit=10) == ["p1"]


def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    _setup(tmp_path)
    fts = PiccoloPaperFTS()

    assert fts.search(" ", limit=10) == []


def test_search_treats_fts_syntax_as_literal_text(tmp_path: Path) -> None:
    _setup(tmp_path)
    fts = PiccoloPaperFTS()

    assert fts.search('unmatched"', limit=10) == []


def test_search_reflects_updated_metadata(tmp_path: Path) -> None:
    _setup(tmp_path)
    store = PiccoloPaperStore()
    store.create_paper({"paper_id": "p1", "title": "Old title", "abstract": "none"})
    store.update_metadata("p1", {"title": "New Transformer Title"})

    fts = PiccoloPaperFTS()
    assert fts.search("Transformer", limit=10) == ["p1"]
