"""Tests for PiccoloPaperExternalIdStore."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloPaperExternalIdStore


@pytest.fixture
def db(tmp_path: Path) -> PiccoloDatabase:
    db = PiccoloDatabase(tmp_path / "test.sqlite")
    db.initialize_schema()
    return db


@pytest.fixture
def store(db: PiccoloDatabase) -> PiccoloPaperExternalIdStore:
    return PiccoloPaperExternalIdStore()


class TestPiccoloPaperExternalIdStore:
    """Tests for PiccoloPaperExternalIdStore."""

    def test_create_and_get_external_ids(self, store: PiccoloPaperExternalIdStore) -> None:
        """Should store and retrieve external IDs for a paper."""
        paper_id = str(uuid.uuid4())
        external_ids = {"ArXiv": "2001.12345", "DOI": "10.1234/abc"}

        store.create_external_ids(paper_id, external_ids)
        result = store.get_external_ids(paper_id)

        assert result == external_ids

    def test_get_external_ids_returns_empty_dict_when_none_exist(
        self, store: PiccoloPaperExternalIdStore
    ) -> None:
        """Should return empty dict when no external IDs exist for paper."""
        paper_id = str(uuid.uuid4())

        result = store.get_external_ids(paper_id)

        assert result == {}

    def test_create_external_ids_with_empty_dict(
        self, store: PiccoloPaperExternalIdStore
    ) -> None:
        """Should handle empty external IDs dict gracefully."""
        paper_id = str(uuid.uuid4())

        store.create_external_ids(paper_id, {})
        result = store.get_external_ids(paper_id)

        assert result == {}

    def test_create_external_ids_overwrites_existing(
        self, store: PiccoloPaperExternalIdStore
    ) -> None:
        """Should handle being called multiple times for same paper."""
        paper_id = str(uuid.uuid4())
        external_ids1 = {"ArXiv": "2001.12345"}
        external_ids2 = {"DOI": "10.1234/abc"}

        store.create_external_ids(paper_id, external_ids1)
        store.create_external_ids(paper_id, external_ids2)
        result = store.get_external_ids(paper_id)

        # Should have both sets of IDs
        assert "ArXiv" in result
        assert "DOI" in result

    def test_multiple_papers_isolated(self, store: PiccoloPaperExternalIdStore) -> None:
        """Should keep external IDs separate per paper."""
        paper_id1 = str(uuid.uuid4())
        paper_id2 = str(uuid.uuid4())
        external_ids1 = {"ArXiv": "2001.12345"}
        external_ids2 = {"DOI": "10.1234/abc"}

        store.create_external_ids(paper_id1, external_ids1)
        store.create_external_ids(paper_id2, external_ids2)

        result1 = store.get_external_ids(paper_id1)
        result2 = store.get_external_ids(paper_id2)

        assert result1 == external_ids1
        assert result2 == external_ids2
