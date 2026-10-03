from __future__ import annotations

from pathlib import Path

import pytest

from papers.app.ideation_contracts import IdeateProjectRequest
from papers.app.use_cases.idea_reviews import IdeaReviewService
from papers.domain.idea_reviews import ReviewInput
from papers.infra.idea_reviews import IdeaReviewStore
from papers.infra.piccolo.database import PiccoloDatabase
from tests.app.use_cases.test_project_ideation import FakeLLM, _critique, _generation, _use_case


def bundle(root: Path) -> Path:
    return _use_case(root, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "offline")
    )


def service(root: Path) -> IdeaReviewService:
    return IdeaReviewService(IdeaReviewStore(PiccoloDatabase(root / "reviews.sqlite")), root)


def test_review_revisions_survive_restart_without_rewriting_old_record(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    desk = service(tmp_path).inspect(path)
    binding = desk.ideas[0].binding
    first = service(tmp_path).record(
        ReviewInput(
            binding=binding,
            reviewer="Researcher A",
            verdict="keep",
            rationale="Promising controlled test.",
            previous_review_id=None,
        )
    )
    second = service(tmp_path).record(
        ReviewInput(
            binding=binding,
            reviewer="Researcher B",
            verdict="revise",
            rationale="Specify the dataset first.",
            previous_review_id=first.review_id,
        )
    )
    restored = service(tmp_path).inspect(path)
    assert restored.ideas[0].reviews == (first, second)
    assert first.rationale == "Promising controlled test."
    assert second.revision == 2
    assert restored.ideas[0].state == "reviewed"
    assert not first.grants_nsqd_approval and not first.verifies_evidence


def test_stale_binding_and_lost_revision_are_rejected(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    binding = service(tmp_path).inspect(path).ideas[0].binding
    request = ReviewInput(
        binding=binding,
        reviewer="Researcher",
        verdict="reject",
        rationale="Insufficient experimental controls.",
        previous_review_id=None,
    )
    service(tmp_path).record(request)
    with pytest.raises(ValueError):
        service(tmp_path).record(request)
    (path / "report.md").write_text("Changed after inspection.")
    with pytest.raises(ValueError):
        service(tmp_path).record(request)


def test_reviewed_plan_links_exact_review_after_restart_without_authority(tmp_path: Path) -> None:
    import json

    from papers.app.ideation_contracts import PlanIdeaRequest
    from papers.app.use_cases.idea_reviews.planning import plan_reviewed_idea
    from papers.app.use_cases.ideation import PlanIdeaUseCase
    from papers.domain.idea_reviews import model_sha256
    from papers.domain.ideation_bundle import BundleType, verify_manifest
    from tests.investigation_plan_test_data import valid_investigation_plan_payload

    path = bundle(tmp_path)
    binding = service(tmp_path).inspect(path).ideas[0].binding
    review = service(tmp_path).record(
        ReviewInput(
            binding=binding,
            reviewer="Researcher",
            verdict="keep",
            rationale="The proposed controlled test is actionable.",
            previous_review_id=None,
        )
    )
    source_bytes = {entry.name: entry.read_bytes() for entry in path.iterdir()}
    llm = FakeLLM(
        [json.dumps(valid_investigation_plan_payload("Do adaptive masks reduce forecast error?"))]
    )
    selection = plan_reviewed_idea(
        service(tmp_path),
        review.review_id,
        PlanIdeaRequest.defaults(path, "idea-1", {}, "offline"),
        PlanIdeaUseCase(llm, tmp_path),
    )
    assert selection.review_sha256 == model_sha256(review)
    assert selection.binding == binding
    assert verify_manifest(tmp_path / selection.plan_bundle, BundleType.selected_idea_plan)
    assert (tmp_path / selection.handoff_bundle / "handoff.json").is_file()
    restored = service(tmp_path).inspect(path)
    assert restored.ideas[0].state == "selected"
    assert restored.ideas[0].selections == (selection,)
    assert {entry.name: entry.read_bytes() for entry in path.iterdir()} == source_bytes
    assert not selection.grants_nsqd_approval
    assert not selection.verifies_evidence
    assert not selection.activates_operator
    assert not (tmp_path / "data/nsqd").exists()
    from papers.app.use_cases.idea_reviews.handoff import verify_selection_artifacts

    for invalid in (
        selection.model_copy(update={"review_sha256": "0" * 64}),
        selection.model_copy(update={"plan_bundle": Path("../outside")}),
        selection.model_copy(update={"plan_manifest_sha256": "0" * 64}),
        selection.model_copy(update={"selection_note": "spoofed selection"}),
    ):
        with pytest.raises(ValueError):
            verify_selection_artifacts(invalid, review, tmp_path)
    extra = tmp_path / selection.handoff_bundle / "extra.txt"
    extra.write_text("unmanifested artifact")
    with pytest.raises(ValueError):
        verify_selection_artifacts(selection, review, tmp_path)
    extra.unlink()
    (tmp_path / selection.plan_bundle / "report.md").write_text("Changed plan.")
    with pytest.raises(ValueError):
        service(tmp_path).inspect(path)


@pytest.mark.parametrize("verdict", ["revise", "reject"])
def test_planning_rejects_non_kept_or_superseded_review(tmp_path: Path, verdict: str) -> None:
    from papers.app.ideation_contracts import PlanIdeaRequest
    from papers.app.use_cases.idea_reviews.planning import plan_reviewed_idea
    from papers.app.use_cases.ideation import PlanIdeaUseCase

    path = bundle(tmp_path)
    binding = service(tmp_path).inspect(path).ideas[0].binding
    first = service(tmp_path).record(
        ReviewInput(
            binding=binding,
            reviewer="Researcher",
            verdict="keep",
            rationale="Initial decision.",
            previous_review_id=None,
        )
    )
    revised = service(tmp_path).record(
        ReviewInput.model_validate(
            {
                "binding": binding,
                "reviewer": "Researcher",
                "verdict": verdict,
                "rationale": "Updated assessment.",
                "previous_review_id": first.review_id,
            }
        )
    )
    llm = FakeLLM([])
    for review in (first, revised):
        with pytest.raises(ValueError):
            plan_reviewed_idea(
                service(tmp_path),
                review.review_id,
                PlanIdeaRequest.defaults(path, "idea-1", {}, "offline"),
                PlanIdeaUseCase(llm, tmp_path),
            )
    assert not llm.calls


def test_database_enforces_immutable_history_and_lazy_reads(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    store = service(tmp_path).store
    assert store.history() == () and store.selections() == ()
    assert not store.database.path.exists()
    path = bundle(tmp_path)
    binding = service(tmp_path).inspect(path).ideas[0].binding
    service(tmp_path).record(
        ReviewInput(
            binding=binding,
            reviewer="Researcher",
            verdict="keep",
            rationale="Record the decision.",
            previous_review_id=None,
        )
    )
    with closing(sqlite3.connect(store.database.path)) as connection:
        for sql in ("DELETE FROM idea_reviews", "UPDATE idea_reviews SET revision=9"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(sql)
    assert len(service(tmp_path).store.history()) == 1


def test_rehashed_bundle_exposes_stale_reviews_without_reusing_them(tmp_path: Path) -> None:
    from tests.app.use_cases.test_project_ideation import _rehash_ideation_bundle

    path = bundle(tmp_path)
    original = service(tmp_path).inspect(path).ideas[0].binding
    review = service(tmp_path).record(
        ReviewInput(
            binding=original,
            reviewer="Researcher",
            verdict="keep",
            rationale="Original bundle assessment.",
            previous_review_id=None,
        )
    )
    (path / "report.md").write_text("Deliberately revised report.")
    _rehash_ideation_bundle(path)
    desk = service(tmp_path).inspect(path)
    assert desk.ideas[0].stale_review_ids == (review.review_id,)
    assert desk.ideas[0].state == "generated"
    with pytest.raises(ValueError, match="changed"):
        service(tmp_path).require_binding(original)


def test_bundle_listing_states_and_workspace_boundary(tmp_path: Path) -> None:
    from papers.domain.idea_reviews import IdeaReviewError

    path = bundle(tmp_path)
    assert service(tmp_path).bundles()[0].state == "generated"
    assert service(tmp_path).bundles("another-project") == ()
    with pytest.raises(IdeaReviewError, match="under output"):
        service(tmp_path).inspect(tmp_path)
    (path / "report.md").write_text("Unverified edit.")
    assert service(tmp_path).bundles()[0].state == "invalid"


def test_decision_cannot_claim_nsqd_authority(tmp_path: Path) -> None:
    from pydantic import ValidationError

    binding = service(tmp_path).inspect(bundle(tmp_path)).ideas[0].binding
    with pytest.raises(ValidationError):
        ReviewInput.model_validate(
            {
                "binding": binding,
                "reviewer": "Researcher",
                "verdict": "keep",
                "rationale": "Candidate experiment",
                "previous_review_id": None,
                "grants_nsqd_approval": True,
            }
        )


def test_review_history_is_portable_without_rewriting_immutable_json(tmp_path: Path) -> None:
    import shutil

    original = tmp_path / "original"
    original.mkdir()
    path = bundle(original)
    binding = service(original).inspect(path).ideas[0].binding
    review = service(original).record(
        ReviewInput(
            binding=binding,
            reviewer="Researcher",
            verdict="keep",
            rationale="Recorded before moving the workspace.",
            previous_review_id=None,
        )
    )
    restored = tmp_path / "restored"
    shutil.copytree(original, restored)
    assert service(restored).inspect(binding.bundle_path).ideas[0].reviews == (review,)
