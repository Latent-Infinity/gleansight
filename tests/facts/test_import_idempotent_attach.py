from __future__ import annotations

from pathlib import Path

from papers.app.use_cases.discovery import ImportCandidateUseCase
from papers.app.use_cases.taxonomy import CreateProjectUseCase, CreateTagUseCase
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAtomicCandidateImport,
    PiccoloCandidateStore,
    PiccoloJobQueue,
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloPaperTagStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)
from papers.infra.piccolo.tables import Job, PaperProject, PaperTag


def test_reimport_attaches_memberships_and_does_not_enqueue_second_download(tmp_path: Path) -> None:
    PiccoloDatabase(tmp_path / "import.sqlite").initialize_schema()
    candidates = PiccoloCandidateStore()
    papers = PiccoloPaperStore()
    jobs = PiccoloJobQueue()
    projects = PiccoloProjectStore()
    tags = PiccoloTagStore()
    use_case = ImportCandidateUseCase(
        candidate_store=candidates,
        paper_store=papers,
        job_queue=jobs,
        project_store=projects,
        tag_store=tags,
        atomic_candidate_import=PiccoloAtomicCandidateImport(),
    )
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
    first = use_case.import_candidate("cand-1")
    project_id = CreateProjectUseCase(project_store=projects)(name="alpha")
    tag_id = CreateTagUseCase(tag_store=tags)(name="ml", tag_type="topic")
    second = use_case.import_candidate("cand-1", project_ids=[project_id], tag_ids=[tag_id])
    assert first == second
    assert Job.count().run_sync() == 1
    assert PiccoloPaperProjectStore().is_attached(first, project_id)
    assert PiccoloPaperTagStore().is_attached(first, tag_id)
    use_case.import_candidate("cand-1", project_ids=[project_id], tag_ids=[tag_id])
    assert PaperProject.count().run_sync() == 1
    assert PaperTag.count().run_sync() == 1
    assert Job.count().run_sync() == 1
