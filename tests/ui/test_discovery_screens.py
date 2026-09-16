from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.screens.acquire import AcquireScreen
from papers.ui.screens.archive import ArchiveScreen
from papers.ui.screens.card import CardScreen
from papers.ui.screens.diverge import DivergeScreen
from papers.ui.screens.gate import GateScreen
from papers.ui.screens.ground import GroundScreen
from papers.ui.screens.harvest import HarvestScreen
from papers.ui.screens.map import MapScreen
from papers.ui.screens.project import ProjectScreen
from papers.ui.screens.rescore import RescoreScreen
from papers.ui.screens.skeleton import SkeletonScreen
from papers.ui.screens.tau import TauScreen


@dataclass
class _Services:
    map_snapshot: object = None
    list_archive_elites: object = None
    get_frontier_card: object = None
    harvest_records: object = None
    diverge_candidate: object = None
    ground_candidate: object = None
    gate_candidate: object = None
    project_records: object = None
    approve_digest: object = None
    acquire_corpus: object = None
    run_paper_jobs: object = None
    rescore_card: object = None
    tau_command: object = None
    run_skeleton_loop: object = None


def _click(button: ft.Button) -> None:
    assert button.on_click is not None
    with patch.object(ft.Control, "update", return_value=None):
        button.on_click(MagicMock())


def test_map_screen_loads_and_renders_cell_statuses() -> None:
    calls: list[dict[str, object]] = []

    def map_snapshot(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "cell_statuses": {"mechanism=flow-driven|target=drawdown|horizon=intraday": "Unknown"},
        }

    screen = MapScreen(_Services(map_snapshot=map_snapshot)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    snapshot_input, _policy_input, _state_input, load = row.controls
    assert isinstance(snapshot_input, ft.TextField)
    assert isinstance(load, ft.Button)
    snapshot_input.value = "snap"

    _click(load)

    assert calls == [
        {
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "snapshot_state": "calibration",
        }
    ]
    output = screen.controls[3]
    assert isinstance(output, ft.Text)
    assert '"Unknown": 1' in str(output.value)


def test_map_screen_reports_validation_and_service_errors() -> None:
    def fail(**_kwargs: object) -> dict[str, object]:
        raise ValueError("unknown snapshot_id")

    screen = MapScreen(_Services(map_snapshot=fail)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    snapshot_input, _policy_input, _state_input, load = row.controls
    assert isinstance(snapshot_input, ft.TextField)
    assert isinstance(load, ft.Button)
    output = screen.controls[3]
    assert isinstance(output, ft.Text)

    _click(load)
    assert output.value == "Snapshot id is required."

    snapshot_input.value = "missing"
    _click(load)
    assert output.value == "Error: unknown snapshot_id"


def test_archive_screen_refreshes_elites_and_empty_state() -> None:
    rows = [
        {
            "card_id": "c1",
            "cell_id": "mechanism=flow-driven|target=drawdown|horizon=intraday",
            "title": "elite",
            "viability": 5,
        }
    ]
    screen = ArchiveScreen(_Services(list_archive_elites=lambda: list(rows))).build()
    assert isinstance(screen, ft.Column)
    refresh = screen.controls[2]
    status = screen.controls[3]
    output = screen.controls[4]
    assert isinstance(refresh, ft.Button)
    assert isinstance(status, ft.Text)
    assert isinstance(output, ft.ListView)

    _click(refresh)
    assert status.value == "1 elite card(s)"
    assert len(output.controls) == 1
    assert "elite" in str(output.controls[0].value)

    rows.clear()
    _click(refresh)
    assert status.value == "No elite cards."
    assert output.controls == []


def test_archive_screen_reports_service_error() -> None:
    def fail() -> list[dict[str, object]]:
        raise RuntimeError("database unavailable")

    screen = ArchiveScreen(_Services(list_archive_elites=fail)).build()
    assert isinstance(screen, ft.Column)
    refresh = screen.controls[2]
    status = screen.controls[3]
    assert isinstance(refresh, ft.Button)
    assert isinstance(status, ft.Text)

    _click(refresh)

    assert status.value == "Error: database unavailable"


def test_card_screen_validates_and_renders_card() -> None:
    calls: list[str] = []

    def get_frontier_card(card_id: str) -> dict[str, object] | None:
        calls.append(card_id)
        return {"card_id": card_id, "title": "Frontier card"}

    screen = CardScreen(_Services(get_frontier_card=get_frontier_card)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    card_input, load = row.controls
    output = screen.controls[3]
    assert isinstance(card_input, ft.TextField)
    assert isinstance(load, ft.Button)
    assert isinstance(output, ft.Text)

    _click(load)
    assert output.value == "Card id is required."
    assert calls == []

    card_input.value = "c1"
    _click(load)
    assert calls == ["c1"]
    assert '"card_id": "c1"' in str(output.value)


def test_card_screen_reports_service_error() -> None:
    def fail(_card_id: str) -> dict[str, object] | None:
        raise RuntimeError("lookup failed")

    screen = CardScreen(_Services(get_frontier_card=fail)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    card_input, load = row.controls
    output = screen.controls[3]
    assert isinstance(card_input, ft.TextField)
    assert isinstance(load, ft.Button)
    assert isinstance(output, ft.Text)
    card_input.value = "c1"

    _click(load)

    assert output.value == "Error: lookup failed"


def test_harvest_screen_runs_configured_service() -> None:
    calls: list[dict[str, object]] = []

    def harvest_records(*, file_path: str) -> dict[str, object]:
        calls.append({"file_path": file_path})
        return {"record_ids": ["r1", "r2"]}

    screen = HarvestScreen(_Services(harvest_records=harvest_records)).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    file_input, run = row.controls
    output = screen.controls[3]
    assert isinstance(file_input, ft.TextField)
    assert isinstance(run, ft.Button)
    _click(run)
    assert output.value == "Harvest file path is required."
    assert calls == []
    file_input.value = "tests/fixtures/harvest.yaml"
    _click(run)
    assert calls == [{"file_path": "tests/fixtures/harvest.yaml"}]
    assert '"accepted": 2' in str(output.value)


def test_harvest_screen_reports_missing_service_and_errors() -> None:
    screen = HarvestScreen(_Services()).build()
    assert isinstance(screen, ft.Column)
    row = screen.controls[2]
    assert isinstance(row, ft.Row)
    file_input, run = row.controls
    output = screen.controls[3]
    file_input.value = "missing.yaml"
    _click(run)
    assert output.value == "Harvest is not configured."

    def fail(*, file_path: str) -> dict[str, object]:
        raise ValueError("essays exhaust")

    screen = HarvestScreen(_Services(harvest_records=fail)).build()
    row = screen.controls[2]
    file_input, run = row.controls
    output = screen.controls[3]
    file_input.value = "bad.yaml"
    _click(run)
    assert output.value == "Error: essays exhaust"


def test_diverge_screen_runs_operator_a_and_rejects_deferred_operators() -> None:
    calls: list[dict[str, object]] = []

    def diverge_candidate(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"candidate_artifact_hash": "ab" * 32}

    screen = DivergeScreen(_Services(diverge_candidate=diverge_candidate)).build()
    assert isinstance(screen, ft.Column)
    form = screen.controls[2]
    assert isinstance(form, ft.Column)
    paths = form.controls[0]
    operator_row = form.controls[1]
    assert isinstance(paths, ft.Row)
    assert isinstance(operator_row, ft.Row)
    fixture, axiom, snapshot, policy = paths.controls
    operator, target, axiom_cell, state, run = operator_row.controls
    output = screen.controls[3]
    _click(run)
    assert "required" in str(output.value).lower()
    fixture.value = "candidate.yaml"
    axiom.value = "predictors assume stationary return signal"
    snapshot.value = "snap"
    operator.value = "C"
    _click(run)
    assert output.value == "Operator must be A or B."
    assert calls == []
    operator.value = "A"
    _click(run)
    assert calls == [
        {
            "candidate_fixture": "candidate.yaml",
            "axiom": "predictors assume stationary return signal",
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "operator": "A",
            "target_cell_id": None,
            "axiom_cell_id": None,
            "snapshot_state": "calibration",
        }
    ]
    assert "abab" in str(output.value)


def test_diverge_screen_requires_cells_for_operator_b() -> None:
    calls: list[dict[str, object]] = []

    def diverge_candidate(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"candidate_artifact_hash": "cd" * 32}

    screen = DivergeScreen(_Services(diverge_candidate=diverge_candidate)).build()
    form = screen.controls[2]
    paths = form.controls[0]
    operator_row = form.controls[1]
    fixture, axiom, snapshot, _policy = paths.controls
    operator, target, axiom_cell, _state, run = operator_row.controls
    output = screen.controls[3]
    fixture.value = "candidate.yaml"
    axiom.value = "whitespace axiom"
    snapshot.value = "snap"
    operator.value = "B"
    _click(run)
    assert "Operator B requires" in str(output.value)
    assert calls == []
    target.value = "cell-a"
    axiom_cell.value = "cell-b"
    _click(run)
    assert calls[0]["operator"] == "B"
    assert calls[0]["target_cell_id"] == "cell-a"
    assert calls[0]["axiom_cell_id"] == "cell-b"


def test_ground_and_gate_screens_validate_and_run() -> None:
    ground_calls: list[dict[str, object]] = []
    gate_calls: list[dict[str, object]] = []

    def ground_candidate(**kwargs: object) -> dict[str, object]:
        ground_calls.append(kwargs)
        return {"grounding_class": "unevaluated"}

    def gate_candidate(**kwargs: object) -> dict[str, object]:
        gate_calls.append(kwargs)
        return {"card_decision": "rejected", "viability": 0, "cell_id": "c"}

    ground = GroundScreen(_Services(ground_candidate=ground_candidate)).build()
    row = ground.controls[2]
    hash_input, snapshot, version, state, run = row.controls
    output = ground.controls[3]
    _click(run)
    assert "required" in str(output.value).lower()
    hash_input.value = "aa" * 32
    snapshot.value = "snap"
    version.value = "11"
    _click(run)
    assert ground_calls == [
        {
            "candidate_artifact_hash": "aa" * 32,
            "snapshot_id": "snap",
            "corpus_version": 11,
            "snapshot_state": "calibration",
        }
    ]
    assert "unevaluated" in str(output.value)

    gate = GateScreen(_Services(gate_candidate=gate_candidate)).build()
    row = gate.controls[2]
    hash_input, snapshot, version, evaluator, state, run = row.controls
    output = gate.controls[3]
    hash_input.value = "bb" * 32
    snapshot.value = "snap"
    version.value = "11"
    evaluator.value = "eval-1"
    _click(run)
    assert gate_calls[0]["evaluator_run_id"] == "eval-1"
    assert "rejected" in str(output.value)


def test_project_screen_projects_and_approves_digest() -> None:
    projected: list[dict[str, object]] = []
    approved: list[str] = []

    def project_records(*, projection_path: str, manifest_path: str) -> dict[str, object]:
        projected.append({"projection_path": projection_path, "manifest_path": manifest_path})
        return {"record_id": "rec-1", "created": True, "snapshot_id": "snap"}

    def approve_digest(*, digest: str) -> dict[str, object]:
        approved.append(digest)
        return {"digest": digest, "approved": True}

    screen = ProjectScreen(
        _Services(project_records=project_records, approve_digest=approve_digest)
    ).build()
    form = screen.controls[2]
    project_row, digest_row = form.controls
    projection, manifest, project_btn = project_row.controls
    digest, confirmation, approve_btn = digest_row.controls
    output = screen.controls[3]
    _click(project_btn)
    assert "required" in str(output.value).lower()
    projection.value = "proj.yaml"
    manifest.value = "manifest.toml"
    _click(project_btn)
    assert projected == [{"projection_path": "proj.yaml", "manifest_path": "manifest.toml"}]
    assert "rec-1" in str(output.value)
    _click(approve_btn)
    assert "Digest" in str(output.value)
    digest.value = "ab" * 32
    confirmation.value = "APPROVE"
    _click(approve_btn)
    assert approved == ["ab" * 32]


def test_acquire_and_paper_jobs_screens_run_services() -> None:
    acquired: list[dict[str, object]] = []
    processed: list[int] = []

    def acquire_corpus(**kwargs: object) -> dict[str, object]:
        acquired.append(kwargs)
        return {"stopped": True, "route": "insufficient"}

    def run_paper_jobs(*, max_jobs: int) -> dict[str, object]:
        processed.append(max_jobs)
        return {"processed": max_jobs}

    screen = AcquireScreen(
        _Services(acquire_corpus=acquire_corpus, run_paper_jobs=run_paper_jobs)
    ).build()
    form = screen.controls[2]
    acquire_row, jobs_row = form.controls
    snapshot, policy, target, decision, acquire_btn = acquire_row.controls
    max_jobs, jobs_btn = jobs_row.controls
    output = screen.controls[3]
    _click(acquire_btn)
    assert "required" in str(output.value).lower()
    snapshot.value = "snap"
    _click(acquire_btn)
    assert acquired[0]["snapshot_id"] == "snap"
    assert acquired[0]["domain_policy_id"] == "finance/1"
    max_jobs.value = "3"
    _click(jobs_btn)
    assert processed == [3]


def test_rescore_tau_and_skeleton_screens_validate_and_run() -> None:
    rescored: list[dict[str, object]] = []
    tau_calls: list[dict[str, object]] = []
    skeletons: list[dict[str, object]] = []

    def rescore_card(**kwargs: object) -> dict[str, object]:
        rescored.append(kwargs)
        return {"status": "succeeded"}

    def tau_command(**kwargs: object) -> dict[str, object]:
        tau_calls.append(kwargs)
        return {"action": kwargs["action"]}

    def run_skeleton_loop(**kwargs: object) -> dict[str, object]:
        skeletons.append(kwargs)
        return {"card_decision": "rejected", "archive_empty": True}

    rescore = RescoreScreen(_Services(rescore_card=rescore_card)).build()
    row = rescore.controls[2]
    card_id, snapshot, version, state, run = row.controls
    output = rescore.controls[3]
    _click(run)
    assert "required" in str(output.value).lower()
    card_id.value = "card-1"
    snapshot.value = "snap"
    version.value = "11"
    _click(run)
    assert rescored[0]["card_id"] == "card-1"
    assert rescored[0]["current_corpus_version"] == 11

    tau = TauScreen(_Services(tau_command=tau_command)).build()
    form = tau.controls[2]
    hashes, action_row = form.controls
    action, output_path, inputs, balanced, run = action_row.controls
    output = tau.controls[3]
    _click(run)
    assert "required" in str(output.value).lower()
    hashes.value = "aa" * 32 + "\n" + "bb" * 32
    action.value = "export"
    _click(run)
    assert tau_calls[0]["hashes"] == ["aa" * 32, "bb" * 32]
    assert tau_calls[0]["action"] == "export"
    action.value = "invent"
    _click(run)
    assert "export, inventory, review, or evaluate" in str(output.value)

    skeleton = SkeletonScreen(_Services(run_skeleton_loop=run_skeleton_loop)).build()
    row = skeleton.controls[2]
    fixture, axiom, run = row.controls
    output = skeleton.controls[3]
    fixture.value = "gamma-flow.yaml"
    axiom.value = "predictors assume stationary return signal"
    _click(run)
    assert skeletons[0]["candidate_fixture"] == "gamma-flow.yaml"
    assert "rejected" in str(output.value)
