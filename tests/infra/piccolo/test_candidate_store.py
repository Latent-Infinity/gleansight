from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloCandidateStore


def _setup_store(tmp_path: Path) -> PiccoloCandidateStore:
    db = PiccoloDatabase(tmp_path / "candidates.sqlite")
    db.initialize_schema()
    return PiccoloCandidateStore()


def test_create_and_get_candidate(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    candidate_id = "cand-1"

    store.create_candidate(
        {
            "candidate_id": candidate_id,
            "source": "semantic_scholar",
            "source_paper_id": "s2-123",
            "title": "Test Paper",
            "year": 2024,
            "venue": "Conference",
            "authors_json": '["Alice", "Bob"]',
            "abstract": "Abstract text",
            "external_ids_json": '{"arxiv": "2401.12345"}',
            "created_at": now,
            "updated_at": now,
        }
    )

    candidate = store.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate["candidate_id"] == candidate_id
    assert candidate["title"] == "Test Paper"
    assert candidate["source"] == "semantic_scholar"
    assert candidate["year"] == 2024


def test_get_nonexistent_candidate(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    candidate = store.get_candidate("nonexistent")
    assert candidate is None


def test_list_candidates_all(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()

    # Create multiple candidates
    for i in range(3):
        store.create_candidate(
            {
                "candidate_id": f"cand-{i}",
                "source": "semantic_scholar",
                "source_paper_id": f"s2-{i}",
                "title": f"Paper {i}",
                "created_at": now,
                "updated_at": now,
            }
        )

    candidates = store.list_candidates()
    assert len(candidates) == 3
    titles = {c["title"] for c in candidates}
    assert titles == {"Paper 0", "Paper 1", "Paper 2"}


def test_list_candidates_not_imported(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()

    # Create candidates - one imported, one not
    store.create_candidate(
        {
            "candidate_id": "cand-1",
            "source": "semantic_scholar",
            "source_paper_id": "s2-1",
            "title": "Not Imported",
            "created_at": now,
            "updated_at": now,
        }
    )

    store.create_candidate(
        {
            "candidate_id": "cand-2",
            "source": "semantic_scholar",
            "source_paper_id": "s2-2",
            "title": "Imported",
            "imported_paper_id": "paper-123",
            "imported_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )

    not_imported = store.list_candidates(imported=False)
    assert len(not_imported) == 1
    assert not_imported[0]["title"] == "Not Imported"


def test_list_candidates_not_rejected(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()

    # Create candidates - one rejected, one not
    store.create_candidate(
        {
            "candidate_id": "cand-1",
            "source": "semantic_scholar",
            "source_paper_id": "s2-1",
            "title": "Not Rejected",
            "created_at": now,
            "updated_at": now,
        }
    )

    store.create_candidate(
        {
            "candidate_id": "cand-2",
            "source": "semantic_scholar",
            "source_paper_id": "s2-2",
            "title": "Rejected",
            "rejected_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )

    not_rejected = store.list_candidates(rejected=False)
    assert len(not_rejected) == 1
    assert not_rejected[0]["title"] == "Not Rejected"


def test_list_candidates_available(tmp_path: Path) -> None:
    """Test listing candidates that are neither imported nor rejected."""
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()

    # Create 4 candidates with different states
    store.create_candidate(
        {
            "candidate_id": "cand-available",
            "source": "semantic_scholar",
            "source_paper_id": "s2-1",
            "title": "Available",
            "created_at": now,
            "updated_at": now,
        }
    )

    store.create_candidate(
        {
            "candidate_id": "cand-imported",
            "source": "semantic_scholar",
            "source_paper_id": "s2-2",
            "title": "Imported",
            "imported_paper_id": "paper-123",
            "imported_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )

    store.create_candidate(
        {
            "candidate_id": "cand-rejected",
            "source": "semantic_scholar",
            "source_paper_id": "s2-3",
            "title": "Rejected",
            "rejected_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )

    store.create_candidate(
        {
            "candidate_id": "cand-available2",
            "source": "semantic_scholar",
            "source_paper_id": "s2-4",
            "title": "Available 2",
            "created_at": now,
            "updated_at": now,
        }
    )

    available = store.list_candidates(imported=False, rejected=False)
    assert len(available) == 2
    titles = {c["title"] for c in available}
    assert titles == {"Available", "Available 2"}


def test_create_candidate_upserts_on_source_and_refreshes_metadata(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()

    first_id = store.create_candidate(
        {
            "candidate_id": "cand-1",
            "source": "semantic_scholar",
            "source_paper_id": "s2-dup",
            "title": "Old Title",
            "year": 2020,
            "authors_json": '["Alice"]',
            "abstract": "old abstract",
            "external_ids_json": '{"DOI":"10.1/old"}',
            "created_at": now,
            "updated_at": now,
        }
    )
    assert first_id == "cand-1"

    second_id = store.create_candidate(
        {
            "candidate_id": "cand-2",
            "source": "semantic_scholar",
            "source_paper_id": "s2-dup",
            "title": "New Title",
            "year": 2024,
            "authors_json": '["Alice", "Bob"]',
            "abstract": "new abstract",
            "external_ids_json": '{"DOI":"10.1/new"}',
            "created_at": now,
            "updated_at": now,
        }
    )
    assert second_id == "cand-1"

    candidate = store.get_candidate("cand-1")
    assert candidate is not None
    assert candidate["title"] == "New Title"
    assert candidate["year"] == 2024
    assert candidate["authors_json"] == '["Alice", "Bob"]'
    assert candidate["abstract"] == "new abstract"
    assert candidate["external_ids_json"] == '{"DOI":"10.1/new"}'
    assert store.get_candidate("cand-2") is None


def test_mark_imported(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    candidate_id = "cand-1"

    store.create_candidate(
        {
            "candidate_id": candidate_id,
            "source": "semantic_scholar",
            "source_paper_id": "s2-123",
            "title": "Test Paper",
            "created_at": now,
            "updated_at": now,
        }
    )

    # Mark as imported
    paper_id = "paper-456"
    store.mark_imported(candidate_id, paper_id)

    # Verify
    candidate = store.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate["imported_paper_id"] == paper_id
    assert candidate["imported_at"] is not None


def test_mark_imported_idempotent(tmp_path: Path) -> None:
    """Test that marking as imported twice doesn't raise error."""
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    candidate_id = "cand-1"

    store.create_candidate(
        {
            "candidate_id": candidate_id,
            "source": "semantic_scholar",
            "source_paper_id": "s2-123",
            "title": "Test Paper",
            "created_at": now,
            "updated_at": now,
        }
    )

    paper_id = "paper-456"
    store.mark_imported(candidate_id, paper_id)

    # Mark again - should not error
    store.mark_imported(candidate_id, paper_id)

    candidate = store.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate["imported_paper_id"] == paper_id


def test_mark_rejected(tmp_path: Path) -> None:
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    candidate_id = "cand-1"

    store.create_candidate(
        {
            "candidate_id": candidate_id,
            "source": "semantic_scholar",
            "source_paper_id": "s2-123",
            "title": "Test Paper",
            "created_at": now,
            "updated_at": now,
        }
    )

    # Mark as rejected
    store.mark_rejected(candidate_id)

    # Verify
    candidate = store.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate["rejected_at"] is not None


def test_mark_rejected_idempotent(tmp_path: Path) -> None:
    """Test that marking as rejected twice doesn't raise error."""
    store = _setup_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    candidate_id = "cand-1"

    store.create_candidate(
        {
            "candidate_id": candidate_id,
            "source": "semantic_scholar",
            "source_paper_id": "s2-123",
            "title": "Test Paper",
            "created_at": now,
            "updated_at": now,
        }
    )

    store.mark_rejected(candidate_id)
    first = store.get_candidate(candidate_id)
    assert first is not None
    first_rejected_at = first["rejected_at"]

    # Mark again - should not error
    store.mark_rejected(candidate_id)

    candidate = store.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate["rejected_at"] == first_rejected_at  # Should not change
