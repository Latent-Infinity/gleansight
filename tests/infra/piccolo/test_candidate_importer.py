from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.domain.errors import NotFoundError
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloCandidateImporter,
    PiccoloCandidateStore,
    PiccoloPaperExternalIdStore,
    PiccoloPaperStore,
)
from papers.infra.piccolo.tables import Candidate, Job, Paper


def _candidate_fields(candidate_id: str, external_ids_json: str | None = None) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "source": "semantic_scholar",
        "source_paper_id": f"source-{candidate_id}",
        "title": "Candidate Paper",
        "year": 2026,
        "venue": "Test",
        "authors_json": '["Ada"]',
        "abstract": "Abstract",
        "external_ids_json": external_ids_json,
        "rejected_at": None,
        "imported_paper_id": None,
        "imported_at": None,
    }


def test_candidate_import_is_atomic_and_idempotent(tmp_path: Path) -> None:
    database = PiccoloDatabase(tmp_path / "candidate-import.sqlite")
    database.initialize_schema()
    candidates = PiccoloCandidateStore()
    candidates.create_candidate(_candidate_fields("candidate", '{"DOI": "10.1/test"}'))
    importer = PiccoloCandidateImporter()

    first_paper_id = importer.import_candidate("candidate")
    second_paper_id = importer.import_candidate("candidate")

    candidate = candidates.get_candidate("candidate")
    assert candidate is not None
    assert candidate["imported_paper_id"] == first_paper_id == second_paper_id
    assert Paper.count().run_sync() == 1
    assert Job.count().run_sync() == 1
    jobs = Job.select().run_sync()
    assert jobs[0]["paper_id"] == first_paper_id
    assert jobs[0]["payload_json"] == '{"external_ids": {"DOI": "10.1/test"}}'


def test_candidate_import_is_safe_under_concurrent_calls(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    database = PiccoloDatabase(tmp_path / "candidate-import-concurrent.sqlite")
    database.initialize_schema()
    PiccoloCandidateStore().create_candidate(_candidate_fields("candidate"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(PiccoloCandidateImporter().import_candidate, "candidate")
            for _ in range(2)
        ]
        paper_ids = [future.result() for future in futures]

    assert paper_ids[0] == paper_ids[1]
    assert Paper.count().run_sync() == 1
    assert Job.count().run_sync() == 1


def test_candidate_import_rolls_back_every_write_on_failure(tmp_path: Path) -> None:
    database = PiccoloDatabase(tmp_path / "candidate-import-rollback.sqlite")
    database.initialize_schema()
    papers = PiccoloPaperStore()
    external_ids = PiccoloPaperExternalIdStore()
    papers.create_paper({"paper_id": "existing", "title": "Existing"})
    external_ids.create_external_ids("existing", {"DOI": "10.1/conflict"})
    candidates = PiccoloCandidateStore()
    candidates.create_candidate(_candidate_fields("candidate", '{"DOI": "10.1/conflict"}'))

    with pytest.raises(sqlite3.IntegrityError):
        PiccoloCandidateImporter().import_candidate("candidate")

    candidate = Candidate.select().where(Candidate.candidate_id == "candidate").first().run_sync()
    assert candidate is not None
    assert candidate["imported_paper_id"] is None
    assert Paper.count().run_sync() == 1
    assert Job.count().run_sync() == 0


def test_candidate_import_rejects_missing_or_rejected_candidate(tmp_path: Path) -> None:
    database = PiccoloDatabase(tmp_path / "candidate-import-invalid.sqlite")
    database.initialize_schema()
    importer = PiccoloCandidateImporter()

    with pytest.raises(NotFoundError):
        importer.import_candidate("missing")

    fields = _candidate_fields("rejected")
    fields["rejected_at"] = datetime.now(UTC)
    PiccoloCandidateStore().create_candidate(fields)
    with pytest.raises(ValueError, match="already rejected"):
        importer.import_candidate("rejected")


def test_candidate_import_tolerates_malformed_optional_json(tmp_path: Path) -> None:
    database = PiccoloDatabase(tmp_path / "candidate-import-json.sqlite")
    database.initialize_schema()
    fields = _candidate_fields("candidate", "not-json")
    fields["authors_json"] = "not-json"
    PiccoloCandidateStore().create_candidate(fields)

    paper_id = PiccoloCandidateImporter().import_candidate("candidate")

    paper = Paper.select().where(Paper.paper_id == paper_id).first().run_sync()
    assert paper is not None
    assert paper["authors_json"] == "[]"
    job = Job.select().first().run_sync()
    assert job is not None
    assert job["payload_json"] == "{}"
