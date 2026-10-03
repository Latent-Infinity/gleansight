from __future__ import annotations

import json

from gleansight.api.runtime import ApiRuntime
from papers.domain.idea_reviews import IdeaReview, ReviewDesk, ReviewSelection
from papers.ui.review_services import build_review_services
from tests.api.papers.fakes import LLM
from tests.app.use_cases.test_idea_reviews import bundle
from tests.investigation_plan_test_data import valid_investigation_plan_payload


def test_desktop_factory_uses_owned_database_and_configured_provider(
    populated: ApiRuntime,
    providers: None,
) -> None:
    path = bundle(populated.repo_root)
    callbacks = build_review_services(populated.papers, repo_root=populated.repo_root)
    desk = ReviewDesk.model_validate(callbacks["review_ideas"](bundle_path=str(path)))
    binding = desk.ideas[0].binding.model_dump(mode="json")
    review = IdeaReview.model_validate(
        callbacks["record_idea_review"](
            binding=binding,
            reviewer="Desktop researcher",
            verdict="keep",
            rationale="Proceed with a bounded test.",
            previous_review_id=None,
        )
    )
    llm = populated.papers.llm_client
    assert isinstance(llm, LLM)
    llm.responses.append(
        json.dumps(valid_investigation_plan_payload("Do adaptive masks reduce forecast error?"))
    )
    selected = ReviewSelection.model_validate(
        callbacks["plan_reviewed_idea"](
            review_id=review.review_id,
            profile_id="local",
            model=None,
            timeout_s=60,
            max_tokens=2000,
            selection_note="Researcher selected the first test.",
        )
    )
    assert selected.review_id == review.review_id
    assert not selected.plan_bundle.is_absolute()
    assert not selected.binding.bundle_path.is_absolute()
    assert callbacks["list_idea_bundles"](project_id="project-1")["bundles"]
    resumed = build_review_services(populated.papers, repo_root=populated.repo_root)
    assert (
        ReviewDesk.model_validate(resumed["review_ideas"](bundle_path=str(path))).ideas[0].state
        == "selected"
    )
