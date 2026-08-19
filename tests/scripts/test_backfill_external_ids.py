from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloCandidateStore,
    PiccoloPaperExternalIdStore,
    PiccoloPaperStore,
)
from scripts.backfill_external_ids import backfill_external_ids


def test_backfill_adds_missing_ids_to_partially_populated_paper(tmp_path: Path) -> None:
    db_path = tmp_path / "backfill.sqlite"
    PiccoloDatabase(db_path).initialize_schema()
    PiccoloPaperStore().create_paper({"paper_id": "paper", "title": "Paper"})
    PiccoloCandidateStore().create_candidate(
        {
            "candidate_id": "candidate",
            "source": "semantic_scholar",
            "source_paper_id": "source",
            "title": "Paper",
            "authors_json": "[]",
            "external_ids_json": '{"DOI": "10.1/test", "ArXiv": "2601.00001"}',
            "imported_paper_id": "paper",
            "imported_at": datetime.now(UTC),
        }
    )
    external_ids = PiccoloPaperExternalIdStore()
    external_ids.create_external_ids("paper", {"DOI": "10.1/test"})

    updated = backfill_external_ids(db_path)

    assert updated == 1
    assert external_ids.get_external_ids("paper") == {
        "DOI": "10.1/test",
        "ArXiv": "2601.00001",
    }


def test_backfill_dry_run_does_not_write(tmp_path: Path) -> None:
    db_path = tmp_path / "backfill-dry.sqlite"
    PiccoloDatabase(db_path).initialize_schema()
    PiccoloPaperStore().create_paper({"paper_id": "paper", "title": "Paper"})
    PiccoloCandidateStore().create_candidate(
        {
            "candidate_id": "candidate",
            "source": "semantic_scholar",
            "source_paper_id": "source",
            "title": "Paper",
            "authors_json": "[]",
            "external_ids_json": '{"DOI": "10.1/test"}',
            "imported_paper_id": "paper",
            "imported_at": datetime.now(UTC),
        }
    )

    updated = backfill_external_ids(db_path, dry_run=True)

    assert updated == 1
    assert PiccoloPaperExternalIdStore().get_external_ids("paper") == {}
