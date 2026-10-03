from __future__ import annotations

from pathlib import Path

from gleansight.api.papers.reviews import BundlePath, RecordReview, inspect, record
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.app.use_cases.idea_reviews import IdeaReviewService
from papers.domain.idea_reviews import IdeaReview, ReviewDesk
from papers.infra.idea_reviews import IdeaReviewStore
from tests.app.use_cases.test_idea_reviews import bundle


def test_api_review_history_uses_owned_database_and_survives_new_runtime(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    runtime = ApiRuntime(ApiConfiguration(repo_root=tmp_path))
    desk = ReviewDesk.model_validate(inspect(runtime, BundlePath(bundle_path=path)))
    saved = IdeaReview.model_validate(
        record(
            runtime,
            RecordReview(
                binding=desk.ideas[0].binding,
                reviewer="API researcher",
                verdict="keep",
                rationale="Suitable first test.",
            ),
        )
    )
    restarted = ApiRuntime(ApiConfiguration(repo_root=tmp_path))
    restored = ReviewDesk.model_validate(inspect(restarted, BundlePath(bundle_path=path)))
    assert restored.ideas[0].reviews == (saved,)
    assert restored.ideas[0].state == "reviewed"
    other = ApiRuntime(ApiConfiguration(repo_root=tmp_path / "another-workspace"))
    assert (
        IdeaReviewService(IdeaReviewStore(other.paper_database), other.repo_root).store.history()
        == ()
    )
    assert not runtime.nsqd_db.exists()


def test_review_api_operations_and_reviewed_plan(populated: ApiRuntime, providers: None) -> None:
    import json

    from gleansight.api.papers.reviews import (
        BundleQuery,
        PlanReview,
        ReviewQuery,
        bundles,
        history,
        operations,
        plan,
    )
    from papers.domain.idea_reviews import ReviewSelection
    from tests.api.papers.fakes import LLM
    from tests.investigation_plan_test_data import valid_investigation_plan_payload

    path = bundle(populated.repo_root)
    desk = ReviewDesk.model_validate(inspect(populated, BundlePath(bundle_path=path)))
    saved = IdeaReview.model_validate(
        record(
            populated,
            RecordReview(
                binding=desk.ideas[0].binding,
                reviewer="API researcher",
                verdict="keep",
                rationale="Bounded first experiment.",
            ),
        )
    )
    llm = populated.papers.llm_client
    assert isinstance(llm, LLM)
    llm.responses.append(
        json.dumps(valid_investigation_plan_payload("Do adaptive masks reduce forecast error?"))
    )
    selected = ReviewSelection.model_validate(
        plan(
            populated,
            PlanReview(
                review_id=saved.review_id,
                selection_note="Select the kept idea.",
                profile_id="local",
            ),
        )
    )
    assert selected.review_id == saved.review_id
    assert not llm.responses
    assert history(populated, ReviewQuery(bundle_path=path, project_id="project-1")) == {
        "reviews": [saved.model_dump(mode="json")]
    }
    assert isinstance(history(populated, ReviewQuery()), dict)
    assert isinstance(bundles(populated, BundleQuery(project_id="project-1")), dict)
    assert len(operations()) == 5
    provenance = json.loads(
        (populated.repo_root / selected.plan_bundle / "provenance.json").read_text()
    )
    assert provenance["model"] == populated.settings.llm.default_model
