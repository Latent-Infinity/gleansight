from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.app.use_cases import (
    AutonomousTauPacketEvaluationUseCase,
    MapSnapshotUseCase,
    TauMeasurementEvidenceUseCase,
)
from nsqd.cli import (
    _build_autonomous_tau_use_case,
    _canonical_json_text,
    _load_autonomous_tau_rows,
    _tau_report_output,
)
from nsqd.harvest import parse_harvest_file
from nsqd.infra.paper_runtime import compose_default_runtime, markdown_reader
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.project_runtime import run_project
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton
from papers.app import use_cases
from papers.app.composition_root import build_container
from papers.config.settings import (
    DEFAULT_OLLAMA_BASE_URL,
    ConfigurationError,
    load_settings,
    packaged_defaults_path,
    public_configuration_error_message,
)
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import (
    PiccoloCandidateImporter,
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloPaperExternalIdStore,
    PiccoloPaperProjectStore,
)
from papers.ui.app import UIServices, run_app
from papers.ui.path_policy import resolve_report_input, resolve_report_output, resolve_ui_input
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

    def _project_records(*, projection_path: str, manifest_path: str) -> dict[str, Any]:
        embedder = nsqd.ctx.embedder
        if embedder is None:
            raise ValueError("embedder is not configured")
        projection = resolve_ui_input(projection_path, repo_root=repo_root, field="projection_path")
        manifest = resolve_ui_input(manifest_path, repo_root=repo_root, field="manifest_path")
        return run_project(
            projection_path=projection,
            manifest_path=manifest,
            db_path=nsqd_db_path,
            index_path=nsqd_index_path,
            embedder=embedder,
        )

    def _approve_digest(*, digest: str) -> dict[str, Any]:
        token = digest.strip().lower()
        if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
            raise ValueError("digest must be a SHA-256 hex digest")
        nsqd_db_path.parent.mkdir(parents=True, exist_ok=True)
        database = PiccoloDatabase(nsqd_db_path)
        database.initialize_schema()
        digest_store = PiccoloApprovedDigestStore(database)
        digest_store.add(token, approved_at=datetime.now(UTC))
        if token not in digest_store.list_digests():
            raise ValueError("approved digest was not persisted")
        return {"digest": token, "approved": True}

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

    def _tau_command(
        *,
        hashes: list[str],
        action: str,
        output_path: str | None,
        input_paths: list[str],
        require_balanced: bool,
    ) -> dict[str, Any]:
        evidence = TauMeasurementEvidenceUseCase(
            candidates=nsqd.ctx.candidates,
            approved_projection_digests=nsqd.ctx.approved_projection_digests,
        )
        if action == "export":
            payload = evidence.export_jsonl(hashes)
            text = (
                payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
            )
            return {"action": action, "jsonl": text}
        if action == "inventory":
            return {"action": action, "inventory": evidence.inventory(hashes)}
        if action == "review":
            report = _tau_report_output(
                resolve_report_output(output_path, repo_root=repo_root, field="output_path")
                if output_path
                else None,
                workflow="autonomous-tau-review",
                filename="review.json",
            )
            result = _build_autonomous_tau_use_case(
                db=nsqd_db_path,
                index=nsqd_index_path,
                config=config_path,
            ).run(hashes)
            report.write_text(_canonical_json_text(result), encoding="utf-8")
            packet = result["packet"]
            return {
                "action": action,
                "output": str(report),
                "packet_digest": result["packet_digest"],
                "approved_pair_count": packet["approved_pair_count"],
            }
        if action == "evaluate":
            if not input_paths:
                raise ValueError("evaluate requires review input paths")
            report = _tau_report_output(
                resolve_report_output(output_path, repo_root=repo_root, field="output_path")
                if output_path
                else None,
                workflow="evaluate-autonomous-tau-reviews",
                filename="evaluation.json",
            )
            rows = _load_autonomous_tau_rows(
                [
                    resolve_report_input(path, repo_root=repo_root, field="input_path")
                    for path in input_paths
                ]
            )
            audit = settings.nsqd.autonomous_tau.audit
            result = AutonomousTauPacketEvaluationUseCase(
                measurement_evidence=evidence,
                audit_policy_revision=audit.policy_revision,
                audit_sample_rate=audit.sample_rate,
            ).run(hashes, rows, require_balanced=require_balanced)
            report.write_text(_canonical_json_text(result), encoding="utf-8")
            return {"action": action, "output": str(report), "result": result}
        raise ValueError("Action must be export, inventory, review, or evaluate.")

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

    candidate_store = PiccoloCandidateStore()
    extraction_store = PiccoloExtractionStore()
    external_id_store = PiccoloPaperExternalIdStore()
    papers_fts = PiccoloPaperFTS()
    ideate_project, plan_idea = build_ideation_callbacks(base, repo_root=repo_root)

    return UIServices(
        discover=use_cases.DiscoverCandidatesUseCase(
            scholar_client=base.scholar_client,
            candidate_store=candidate_store,
        ),
        import_candidate=use_cases.ImportCandidateUseCase(
            candidate_store=candidate_store,
            paper_store=base.paper_store,
            job_queue=base.job_queue,
            external_id_store=external_id_store,
            atomic_importer=PiccoloCandidateImporter(),
            project_store=base.project_store,
            tag_store=base.tag_store,
            atomic_candidate_import=base.atomic_candidate_import,
        ),
        reject_candidate=use_cases.RejectCandidateUseCase(
            candidate_store=candidate_store,
        ),
        search=use_cases.SearchPapersUseCase(
            papers_fts=papers_fts,
            vector_index=base.vector_index,
            embedder=base.embedder,
        ),
        filter_extractions=use_cases.FilterByExtractionsUseCase(extraction_store=extraction_store),
        aggregate_extractions=use_cases.AggregateExtractionsUseCase(
            extraction_store=extraction_store
        ),
        get_candidate=candidate_store.get_candidate,
        list_paper=base.paper_store.get,
        list_runs=base.analysis_store.list_runs,
        list_jobs=lambda status, limit: base.job_queue.list_jobs(status=status, limit=limit),
        run_next_job=lambda: base.job_runner.run_next(datetime.now(UTC)),
        enqueue_job=lambda job_type, paper_id, run_id, payload: base.job_queue.enqueue(
            job_type, paper_id, run_id, payload
        ),
        cancel_job=base.job_queue.cancel,
        delete_job=base.job_queue.delete_job,
        bulk_delete_jobs=base.job_queue.bulk_delete_jobs,
        bulk_cancel_jobs=base.job_queue.bulk_cancel_jobs,
        get_paper_markdown=markdown_reader(base.blob_store),
        list_extractions=extraction_store.list_by_paper,
        delete_paper=base.paper_store.delete_paper,
        reset_pipeline_stage=base.paper_store.reset_pipeline_stage,
        synthesize_from_corpus=use_cases.SynthesizeFromCorpusUseCase(
            embedder=base.embedder,
            vector_index=base.vector_index,
            paper_store=base.paper_store,
            blob_store=base.blob_store,
            llm_client=base.llm_client,
            paper_project_store=PiccoloPaperProjectStore(),
        ),
        ui_settings={
            "search_max_results": settings.ui.search_max_results,
            "scholar_api_key_set": bool(settings.scholar.api_key),
            "scholar_rate_limit": settings.scholar.rate_limit_per_second,
            "require_open_access": settings.scholar.require_open_access,
        },
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
        project_records=_project_records,
        approve_digest=_approve_digest,
        acquire_corpus=_acquire_corpus,
        run_paper_jobs=_run_paper_jobs,
        rescore_card=_rescore_card,
        tau_command=_tau_command,
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
