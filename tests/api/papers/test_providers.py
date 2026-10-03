import json
from pathlib import Path

import pytest

from gleansight.api.models import OperationError
from gleansight.api.runtime import ApiRuntime
from papers.domain.ideation_bundle import BundleType, verify_manifest
from tests.api.papers.fakes import LLM
from tests.api.papers.support import call, identifier, items, record
from tests.app.use_cases.test_project_ideation import _critique, _generation
from tests.investigation_plan_test_data import valid_investigation_plan_payload


def readable_project(runtime: ApiRuntime) -> str:
    project_id = identifier(
        call(runtime, "projects.create", {"name": "Grounded research"}), "project_id"
    )
    call(runtime, "projects.attach", {"paper_id": "paper-1", "project_id": project_id})
    runtime.papers.blob_store.put_markdown(
        "paper-1", "# Methods\nThe method predicts masked representations. " * 12
    )
    return project_id


def test_discovery_preserves_offset(populated: ApiRuntime, providers: None) -> None:
    # Given / When
    result = call(
        populated,
        "candidates.discover",
        {"query": "learning", "offset": 17, "filters": {"year_min": 2020}},
    )
    # Then
    assert isinstance(result, dict)
    found = items(populated, "candidates.list", {"status": "pending"})
    assert len(found) == 1
    assert found[0]["source_paper_id"] == "s2-17"
    assert (
        record(populated, "candidates.get", {"candidate_id": found[0]["candidate_id"]})["title"]
        == "Discovered locally"
    )


def test_vector_rebuild_feeds_search(populated: ApiRuntime, providers: None) -> None:
    # Given
    readable_project(populated)
    # When
    result = call(populated, "indexes.rebuild-vector", {})
    # Then
    assert result == {"processed": 1}
    search = call(populated, "query.search", {"query": "learning"})
    assert isinstance(search, list) and isinstance(search[0], dict)
    assert search[0]["paper_id"] == "paper-1"


def test_fts_rebuild_restores_real_search(populated: ApiRuntime) -> None:
    # Given
    populated.paper_database.execute("DELETE FROM papers_fts")
    # When
    result = call(populated, "indexes.rebuild-fts", {})
    # Then
    assert result == {"processed": 1}
    rows = populated.paper_database.fetchall(
        "SELECT paper_id FROM papers_fts WHERE papers_fts MATCH ?", ["adaptive"]
    )
    assert rows == [{"paper_id": "paper-1"}]


def test_synthesis_uses_project_evidence(populated: ApiRuntime, providers: None) -> None:
    # Given
    project_id = readable_project(populated)
    call(populated, "indexes.rebuild-vector", {})
    from papers.app.use_cases.synthesis_sources import SynthesisRetrieval

    base = populated.papers
    sources = SynthesisRetrieval(
        base.embedder,
        base.vector_index,
        base.paper_store,
        base.blob_store,
        base.paper_project_store,
    ).retrieve("What is learned?", project_id, 5)
    llm = base.llm_client
    assert isinstance(llm, LLM)
    llm.responses.append(
        json.dumps(
            {
                "status": "supported",
                "claims": [
                    {
                        "text": "Masked representations are learned.",
                        "references": [source.model_dump() for source in sources],
                    }
                ],
                "limitations": [],
            }
        )
    )
    # When
    result = record(
        populated,
        "synthesis.ask",
        {
            "question": "What is learned?",
            "project_id": project_id,
            "profile_id": "local",
            "model": "fake",
        },
    )
    # Then
    assert "Masked representations are learned." in str(result["answer"])
    assert result["sources"] == [source.model_dump() for source in sources]


def test_ideation_and_selected_plan_write_verified_bundles(
    populated: ApiRuntime, providers: None
) -> None:
    # Given
    project_id = readable_project(populated)
    llm = populated.papers.llm_client
    assert isinstance(llm, LLM)
    llm.responses.extend([_generation(), _critique()])
    bundle = identifier(
        call(
            populated,
            "research.ideate-project",
            {
                "project_id": project_id,
                "question": "Find a testable gap",
                "profile_id": "local",
                "model": "fake",
            },
        ),
        "bundle",
    )
    verify_manifest(Path(bundle), BundleType.project_ideation)
    llm.responses.append(
        json.dumps(valid_investigation_plan_payload("Do adaptive masks reduce forecast error?"))
    )
    # When
    result = call(
        populated,
        "research.plan-idea",
        {
            "bundle_path": bundle,
            "idea_id": "idea-1",
            "selection_note": "Evaluate adaptive masking",
            "profile_id": "local",
            "model": "fake",
        },
    )
    # Then
    planned = Path(identifier(result, "bundle"))
    verify_manifest(planned, BundleType.selected_idea_plan)
    assert (planned / "investigation-plan.json").is_file()
    assert (planned / "report.md").stat().st_size > 0


def test_plan_outside_output_is_rejected_before_provider(runtime: ApiRuntime) -> None:
    # Given / When / Then
    with pytest.raises(OperationError, match="under output"):
        call(
            runtime,
            "research.plan-idea",
            {"bundle_path": str(runtime.repo_root), "idea_id": "idea", "selection_note": "Review"},
        )
    assert not (runtime.repo_root / "data").exists()


def test_run_next_empty_queue_reports_no_work(populated: ApiRuntime, providers: None) -> None:
    # Given / When
    result = call(populated, "jobs.run-next", {})
    # Then
    assert result == {"processed": False}
