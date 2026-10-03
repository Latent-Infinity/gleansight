from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import flet as ft
import pytest

from papers.ui.path_policy import resolve_report_bundle, resolve_report_input, resolve_ui_input
from papers.ui.screens.archive import ArchiveScreen
from papers.ui.screens.ideation import IdeationScreen
from papers.ui.screens.project import ProjectScreen
from papers.ui.screens.tau import TauScreen
from tests.ui.fake_services import built_column as _column
from tests.ui.fake_services import built_field as _field
from tests.ui.fake_services import built_row as _row
from tests.ui.fake_services import built_text as _text
from tests.ui.fake_services import complete_ui_services
from tests.ui.fake_services import row_fields_and_button as _row_fields_and_button


@dataclass
class _Services:
    ideate_project: object = None
    plan_idea: object = None
    list_archive_elites: object = None
    rank_archive: object = None
    approve_digest: object = None
    project_records: object = None
    tau_command: object = None


def _click(button: ft.Button) -> None:
    on_click = getattr(button, "on_click")
    assert callable(on_click)
    with patch.object(ft.Control, "update", return_value=None):
        on_click(MagicMock())


def test_ideation_screen_runs_bounded_generation_and_planning() -> None:
    ideation_calls: list[dict[str, object]] = []
    planning_calls: list[dict[str, object]] = []

    def ideate_project(**kwargs: object) -> dict[str, object]:
        ideation_calls.append(kwargs)
        return {"bundle": "output/project-ideation/run"}

    def plan_idea(**kwargs: object) -> dict[str, object]:
        planning_calls.append(kwargs)
        return {"bundle": "output/plan-idea/run"}

    screen = _column(
        IdeationScreen(
            complete_ui_services(_Services(ideate_project=ideate_project, plan_idea=plan_idea))
        ).build()
    )
    assert isinstance(screen, ft.Column)
    description = screen.controls[1]
    ideate_form = screen.controls[2]
    plan_form = screen.controls[3]
    output = _text(screen.controls[4])
    assert isinstance(description, ft.Text)
    assert description.data == "non-authorizing"
    assert isinstance(ideate_form, ft.Column)
    assert isinstance(plan_form, ft.Column)

    project_id, question = (_field(control) for control in _row(ideate_form.controls[0]).controls)
    profile, model, critic_model = (
        _field(control) for control in _row(ideate_form.controls[1]).controls
    )
    ideate_fields, ideate = _row_fields_and_button(_row(ideate_form.controls[2]))
    max_papers, excerpt_bytes, max_excerpts, timeout, max_tokens = ideate_fields
    project_id.value = "project-1"
    question.value = "What testable gaps remain?"
    _click(ideate)

    assert ideation_calls == [
        {
            "project_id": "project-1",
            "question": "What testable gaps remain?",
            "profile_id": None,
            "model": None,
            "critic_model": None,
            "max_papers": 12,
            "excerpt_bytes": 1200,
            "max_excerpts_per_paper": 6,
            "timeout_s": 300,
            "max_tokens": 8000,
        }
    ]
    assert "project-ideation" in str(output.value)

    bundle, idea_id = (_field(control) for control in _row(plan_form.controls[0]).controls)
    plan_profile, plan_model, plan_timeout, plan_tokens = (
        _field(control) for control in _row(plan_form.controls[1]).controls
    )
    plan_fields, plan = _row_fields_and_button(_row(plan_form.controls[2]))
    selection_note = plan_fields[0]
    assert project_id.width == question.width == 320
    assert bundle.width == idea_id.width == selection_note.width == 320
    bundle.value = "output/project-ideation/run"
    idea_id.value = "idea-1"
    _click(plan)

    assert planning_calls == [
        {
            "bundle_path": "output/project-ideation/run",
            "idea_id": "idea-1",
            "profile_id": None,
            "model": None,
            "timeout_s": 300,
            "max_tokens": 8000,
            "selection_note": "operator-selected draft idea",
        }
    ]
    assert profile.value == ""
    assert model.value == ""
    assert critic_model.value == ""
    assert plan_profile.value == ""
    assert plan_model.value == ""


def test_archive_screen_runs_policy_scoped_rank_guard() -> None:
    calls: list[dict[str, object]] = []

    def rank_archive(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"elites": 2, "rank": {"allowed": False, "reason": "rank_guard_blocked"}}

    screen = _column(
        ArchiveScreen(complete_ui_services(_Services(rank_archive=rank_archive))).build()
    )
    rank_form = _row(screen.controls[5])
    rank_output = _text(screen.controls[6])
    rank_fields, rank = _row_fields_and_button(rank_form)
    snapshot, policy, state = rank_fields
    _click(rank)
    assert "required" in str(rank_output.value).lower()
    snapshot.value = "snap-1"
    _click(rank)

    assert calls == [
        {
            "snapshot_id": "snap-1",
            "domain_policy_id": "finance/1",
            "snapshot_state": "calibration",
        }
    ]
    assert "rank_guard_blocked" in str(rank_output.value)
    assert policy.value == "finance/1"
    assert state.value == "calibration"


def test_digest_approval_requires_explicit_confirmation() -> None:
    approved: list[str] = []

    def approve_digest(*, digest: str) -> dict[str, object]:
        approved.append(digest)
        return {"digest": digest, "approved": True}

    screen = _column(
        ProjectScreen(complete_ui_services(_Services(approve_digest=approve_digest))).build()
    )
    digest_row = _row(_column(screen.controls[2]).controls[1])
    digest_fields, approve = _row_fields_and_button(digest_row)
    digest, confirmation = digest_fields
    assert digest.width == 320
    assert digest_row.wrap is True
    digest.value = "ab" * 32
    _click(approve)
    assert approved == []

    confirmation.value = "APPROVE"
    _click(approve)
    assert approved == ["ab" * 32]
    assert confirmation.value == ""

    digest.value = "cd" * 32
    _click(approve)
    assert approved == ["ab" * 32]


def test_digest_approval_consumes_confirmation_before_callback_failure() -> None:
    def approve_digest(*, digest: str) -> dict[str, object]:
        raise RuntimeError(digest)

    screen = _column(
        ProjectScreen(complete_ui_services(_Services(approve_digest=approve_digest))).build()
    )
    digest_row = _row(_column(screen.controls[2]).controls[1])
    digest_fields, approve = _row_fields_and_button(digest_row)
    digest, confirmation = digest_fields
    digest.value = "ab" * 32
    confirmation.value = "APPROVE"

    _click(approve)

    assert confirmation.value == ""


def test_tau_evaluate_requires_review_inputs_and_states_non_authority() -> None:
    calls: list[dict[str, object]] = []

    def tau_command(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"action": "evaluate"}

    screen = _column(TauScreen(complete_ui_services(_Services(tau_command=tau_command))).build())
    description = _text(screen.controls[1])
    form = _column(screen.controls[2])
    hashes = _field(form.controls[0])
    action_row = _row(form.controls[1])
    action_fields, run = _row_fields_and_button(action_row)
    action, _output_path, inputs, _balanced = action_fields
    output = _text(screen.controls[3])
    assert description.data == "report-only-non-authorizing"

    hashes.value = "aa" * 32
    action.value = "evaluate"
    _click(run)
    assert calls == []
    assert "review input" in str(output.value).lower()
    assert action_row.wrap is True
    assert inputs.value == ""


def test_ui_path_policy_rejects_protected_repo_inputs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    protected = repo_root / ".env"
    protected.write_text("TOKEN=secret", encoding="utf-8")
    safe = repo_root / "tests" / "fixtures" / "candidate.yaml"
    safe.parent.mkdir(parents=True)
    safe.write_text("candidate: {}", encoding="utf-8")
    review = repo_root / "output" / "review.json"
    review.parent.mkdir()
    review.write_text("{}", encoding="utf-8")
    bundle = repo_root / "output" / "project-ideation" / "run"
    bundle.mkdir(parents=True)

    with pytest.raises(ValueError, match="protected"):
        resolve_ui_input(".env", repo_root=repo_root, field="candidate fixture")

    assert (
        resolve_ui_input(
            "tests/fixtures/candidate.yaml", repo_root=repo_root, field="candidate fixture"
        )
        == safe
    )
    assert (
        resolve_report_input("output/review.json", repo_root=repo_root, field="review input")
        == review
    )
    assert (
        resolve_report_bundle(
            "output/project-ideation/run", repo_root=repo_root, field="ideation bundle"
        )
        == bundle
    )
