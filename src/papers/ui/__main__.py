from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import yaml

from nsqd.app.use_cases import MapSnapshotUseCase
from nsqd.harvest import parse_harvest_file
from nsqd.infra.paper_runtime import compose_default_runtime
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton
from papers.app.composition_root import build_container
from papers.config.settings import (
    DEFAULT_OLLAMA_BASE_URL,
    ConfigurationError,
    load_settings,
    packaged_defaults_path,
    public_configuration_error_message,
)
from papers.ui.app import UIServices, run_app
from papers.ui.paper_services import build_paper_service_values, build_projection_callbacks
from papers.ui.path_policy import resolve_ui_input
from papers.ui.tau_services import build_tau_callback
from papers.ui.workflow_services import build_ideation_callbacks, build_rank_callback


def build_ui_services(
    config_path: Path | None = None,
    llm_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: str | None = None,
) -> UIServices:
    """Build UIServices container with all dependencies wired."""
    settings = load_settings(defaults_path=packaged_defaults_path(), override_path=config_path)
    base = build_container(
        settings,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
    )

    runtime = compose_default_runtime(
        papers=base,
        nsqd_db_path=Path(settings.data.root) / "nsqd" / "nsqd.sqlite",
        nsqd_index_path=Path(settings.data.root) / "nsqd" / "corpus.lancedb",
        llm_base_url=llm_base_url,
    )
    nsqd = runtime.nsqd
    repo_root = Path.cwd()

    def _harvest_records(*, file_path: str) -> dict[str, Any]:
        source = resolve_ui_input(file_path, repo_root=repo_root, field="file_path")
        payload = parse_harvest_file(source)
        return run_job(
            nsqd,
            "harvest",
            {"filename": str(source), "payload": payload},
            nsqd.clock.now(),
        )

    def _diverge_candidate(
        *,
        candidate_fixture: str,
        axiom: str,
        snapshot_id: str,
        domain_policy_id: str,
        operator: str,
        target_cell_id: str | None,
        axiom_cell_id: str | None,
        snapshot_state: str,
    ) -> dict[str, Any]:
        operator_id = operator.strip().upper()
        if operator_id not in {"A", "B"}:
            raise ValueError("Operator must be A or B.")
        if operator_id == "B" and (not target_cell_id or not axiom_cell_id):
            raise ValueError("Operator B requires target cell id and axiom cell id.")
        fixture = resolve_ui_input(
            candidate_fixture, repo_root=repo_root, field="candidate_fixture"
        )
        loaded = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("candidate fixture must be a mapping")
        now = nsqd.clock.now()
        mapped = run_job(
            nsqd,
            "map",
            {
                "snapshot_id": snapshot_id,
                "domain_policy_id": domain_policy_id,
                "snapshot_state": snapshot_state,
            },
            now,
        )
        diverge_payload: dict[str, Any] = {
            "candidate": loaded,
            "axiom": axiom,
            "operator": operator_id,
            "generator_run_id": str(uuid.uuid4()),
            "cell_statuses": mapped["cell_statuses"],
        }
        if target_cell_id is not None:
            diverge_payload["target_cell_id"] = target_cell_id
        if axiom_cell_id is not None:
            diverge_payload["axioms"] = [{"statement": axiom, "cell_id": axiom_cell_id}]
        return run_job(nsqd, "diverge", diverge_payload, now)

    def _ground_candidate(
        *,
        candidate_artifact_hash: str,
        snapshot_id: str,
        corpus_version: int,
        snapshot_state: str,
    ) -> dict[str, Any]:
        return run_job(
            nsqd,
            "ground",
            {
                "candidate_artifact_hash": candidate_artifact_hash,
                "snapshot_id": snapshot_id,
                "corpus_version": corpus_version,
                "snapshot_state": snapshot_state,
            },
            nsqd.clock.now(),
        )

    def _gate_candidate(
        *,
        candidate_artifact_hash: str,
        snapshot_id: str,
        corpus_version: int,
        evaluator_run_id: str,
        snapshot_state: str,
    ) -> dict[str, Any]:
        return run_job(
            nsqd,
            "score",
            {
                "candidate_artifact_hash": candidate_artifact_hash,
                "snapshot_id": snapshot_id,
                "corpus_version": corpus_version,
                "evaluator_run_id": evaluator_run_id,
                "snapshot_state": snapshot_state,
            },
            nsqd.clock.now(),
        )

    nsqd_db_path = Path(settings.data.root) / "nsqd" / "nsqd.sqlite"
    nsqd_index_path = Path(settings.data.root) / "nsqd" / "corpus.lancedb"

    def _acquire_corpus(
        *,
        snapshot_id: str,
        domain_policy_id: str,
        target: str,
        human_decision: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "domain_policy_id": domain_policy_id,
            "target": target,
        }
        if human_decision is not None:
            payload["human_decision"] = human_decision
        return run_job(nsqd, "acquire", payload, nsqd.clock.now())

    def _run_paper_jobs(*, max_jobs: int) -> dict[str, Any]:
        if max_jobs < 1:
            raise ValueError("max_jobs must be >= 1")
        processed = 0
        while processed < max_jobs and runtime.paper_runner.run_next(nsqd.clock.now()):
            processed += 1
        return {"processed": processed}

    def _rescore_card(
        *,
        card_id: str,
        current_snapshot_id: str,
        current_corpus_version: int,
        snapshot_state: str,
    ) -> dict[str, Any]:
        return run_job(
            nsqd,
            "rescore",
            {
                "card_id": card_id,
                "current_snapshot_id": current_snapshot_id,
                "current_corpus_version": current_corpus_version,
                "snapshot_state": snapshot_state,
            },
            nsqd.clock.now(),
        )

    def _run_skeleton_loop(*, candidate_fixture: str, axiom: str) -> dict[str, Any]:
        fixture = resolve_ui_input(
            candidate_fixture, repo_root=repo_root, field="candidate_fixture"
        )
        return run_skeleton(
            fixture_path=fixture,
            axiom=axiom,
            db_path=nsqd_db_path,
            index_path=nsqd_index_path,
        )

    ideate_project, plan_idea = build_ideation_callbacks(base, repo_root=repo_root)
    project_records, approve_digest = build_projection_callbacks(
        nsqd,
        repo_root=repo_root,
        db_path=nsqd_db_path,
        index_path=nsqd_index_path,
    )

    return UIServices(
        **build_paper_service_values(base, settings),
        map_snapshot=lambda **kwargs: MapSnapshotUseCase(
            snapshots=nsqd.ctx.snapshots,
            records=nsqd.ctx.records,
            morph=nsqd.ctx.morph,
            clock=nsqd.clock,
        ).run(**kwargs),
        list_archive_elites=nsqd.ctx.cards.list_elites,
        get_frontier_card=nsqd.ctx.cards.get_card,
        harvest_records=_harvest_records,
        diverge_candidate=_diverge_candidate,
        ground_candidate=_ground_candidate,
        gate_candidate=_gate_candidate,
        project_records=project_records,
        approve_digest=approve_digest,
        acquire_corpus=_acquire_corpus,
        run_paper_jobs=_run_paper_jobs,
        rescore_card=_rescore_card,
        tau_command=build_tau_callback(
            nsqd,
            settings,
            repo_root=repo_root,
            db_path=nsqd_db_path,
            index_path=nsqd_index_path,
            config_path=config_path,
        ),
        run_skeleton_loop=_run_skeleton_loop,
        ideate_project=ideate_project,
        plan_idea=plan_idea,
        rank_archive=build_rank_callback(nsqd),
    )


def main(
    config: str | None = None,
    llm_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: str | None = None,
) -> None:
    """Launch the Gleansight UI application."""
    config_path = Path(config) if config else None
    try:
        services = build_ui_services(
            config_path=config_path,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
        )
    except ConfigurationError as exc:
        raise SystemExit(public_configuration_error_message(exc)) from None
    run_app(services)


if __name__ == "__main__":
    main()
