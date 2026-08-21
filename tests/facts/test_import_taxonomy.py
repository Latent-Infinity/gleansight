from __future__ import annotations

from pathlib import Path

import pytest

from papers.app.use_cases.discovery import ImportCandidateUseCase
from papers.app.use_cases.taxonomy import CreateProjectUseCase, CreateTagUseCase
from papers.domain.errors import ConflictError, NotFoundError
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAtomicCandidateImport,
    PiccoloCandidateStore,
    PiccoloJobQueue,
    PiccoloPaperExternalIdStore,
    PiccoloPaperStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)
from papers.infra.piccolo.tables import Candidate, Job, Paper, PaperProject, PaperTag


def _setup(
    tmp_path: Path,
) -> tuple[ImportCandidateUseCase, str, str, PiccoloPaperStore, PiccoloCandidateStore]:
    db = PiccoloDatabase(tmp_path / "import.sqlite")
    db.initialize_schema()
    projects = PiccoloProjectStore()
    tags = PiccoloTagStore()
    candidates = PiccoloCandidateStore()
    papers = PiccoloPaperStore()
    jobs = PiccoloJobQueue()
    atomic = PiccoloAtomicCandidateImport()
    use_case = ImportCandidateUseCase(
        candidate_store=candidates,
        paper_store=papers,
        job_queue=jobs,
        external_id_store=PiccoloPaperExternalIdStore(),
        project_store=projects,
        tag_store=tags,
        atomic_candidate_import=atomic,
    )
    candidates.create_candidate(
        {
            "candidate_id": "cand-1",
            "source": "semantic_scholar",
            "source_paper_id": "s2-1",
            "title": "Imported Paper",
            "year": 2024,
            "venue": "Test",
            "authors_json": '["Ada"]',
            "abstract": "Abstract",
            "external_ids_json": '{"DOI": "10.1/test"}',
            "rejected_at": None,
            "imported_paper_id": None,
            "imported_at": None,
        }
    )
    project_id = CreateProjectUseCase(project_store=projects)(name="alpha")
    tag_id = CreateTagUseCase(tag_store=tags)(name="ml", tag_type="topic")
    return use_case, project_id, tag_id, papers, candidates


def test_import_attaches_project_and_tag(tmp_path: Path) -> None:
    use_case, project_id, tag_id, papers, candidates = _setup(tmp_path)
    paper_id = use_case.import_candidate(
        "cand-1",
        project_ids=[project_id],
        tag_ids=[tag_id],
    )
    paper = papers.get(paper_id)
    assert paper is not None
    assert paper["title"] == "Imported Paper"
    candidate = candidates.get_candidate("cand-1")
    assert candidate is not None
    assert candidate["imported_paper_id"] == paper_id
    assert PaperProject.count().run_sync() == 1
    assert PaperTag.count().run_sync() == 1
    assert Job.count().run_sync() == 1


def test_unknown_project_id_creates_nothing(tmp_path: Path) -> None:
    use_case, _project_id, _tag_id, _papers, _candidates = _setup(tmp_path)
    with pytest.raises(NotFoundError, match="project"):
        use_case.import_candidate("cand-1", project_ids=["missing-project"], tag_ids=[])
    assert Paper.count().run_sync() == 0
    candidate = Candidate.select().where(Candidate.candidate_id == "cand-1").first().run_sync()
    assert candidate is not None
    assert candidate["imported_paper_id"] is None
    assert Job.count().run_sync() == 0


def test_mid_transaction_failure_rolls_back_paper_and_import_mark(tmp_path: Path) -> None:
    PiccoloDatabase(tmp_path / "import.sqlite").initialize_schema()
    candidates = PiccoloCandidateStore()
    candidates.create_candidate(
        {
            "candidate_id": "cand-1",
            "source": "semantic_scholar",
            "source_paper_id": "s2-1",
            "title": "Imported Paper",
            "year": 2024,
            "venue": "Test",
            "authors_json": "[]",
            "abstract": "Abstract",
            "external_ids_json": None,
            "rejected_at": None,
            "imported_paper_id": None,
            "imported_at": None,
        }
    )
    atomic = PiccoloAtomicCandidateImport(fail_after_paper_insert=True)
    use_case = ImportCandidateUseCase(
        candidate_store=candidates,
        paper_store=PiccoloPaperStore(),
        job_queue=PiccoloJobQueue(),
        project_store=PiccoloProjectStore(),
        tag_store=PiccoloTagStore(),
        atomic_candidate_import=atomic,
    )
    with pytest.raises(ValueError, match="injected failure"):
        use_case.import_candidate("cand-1")
    assert Paper.count().run_sync() == 0
    candidate = Candidate.select().where(Candidate.candidate_id == "cand-1").first().run_sync()
    assert candidate is not None
    assert candidate["imported_paper_id"] is None
    assert Job.count().run_sync() == 0


def test_adapter_revalidates_taxonomy_ids_inside_transaction(tmp_path: Path) -> None:
    use_case, _project_id, _tag_id, _papers, _candidates = _setup(tmp_path)
    atomic_import = use_case.atomic_candidate_import
    assert atomic_import is not None
    with pytest.raises(NotFoundError, match="project"):
        atomic_import.import_new(
            candidate_id="cand-1",
            paper_fields={"title": "Imported Paper"},
            external_ids={},
            project_ids=["missing-project"],
            tag_ids=[],
        )
    assert Paper.count().run_sync() == 0
    assert Job.count().run_sync() == 0


def test_attach_rejects_stale_paper_id_without_orphan_memberships(tmp_path: Path) -> None:
    use_case, project_id, tag_id, _papers, _candidates = _setup(tmp_path)
    atomic_import = use_case.atomic_candidate_import
    assert atomic_import is not None
    with pytest.raises(NotFoundError, match="paper"):
        atomic_import.attach_to_imported(
            paper_id="missing-paper",
            project_ids=[project_id],
            tag_ids=[tag_id],
        )
    assert PaperProject.count().run_sync() == 0
    assert PaperTag.count().run_sync() == 0


def test_duplicate_external_id_raises_stable_conflict(tmp_path: Path) -> None:
    use_case, _project_id, _tag_id, _papers, candidates = _setup(tmp_path)
    use_case.import_candidate("cand-1")
    candidates.create_candidate(
        {
            "candidate_id": "cand-2",
            "source": "semantic_scholar",
            "source_paper_id": "s2-2",
            "title": "Conflicting Paper",
            "authors_json": "[]",
            "external_ids_json": '{"DOI": "10.1/test"}',
            "rejected_at": None,
            "imported_paper_id": None,
        }
    )

    with pytest.raises(ConflictError, match="external identifier"):
        use_case.import_candidate("cand-2")

    assert Paper.count().run_sync() == 1
    assert Job.count().run_sync() == 1
