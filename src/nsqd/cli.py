from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
import yaml

from nsqd.app.use_cases import (
    AutonomousTauLabelingUseCase,
    AutonomousTauPacketEvaluationUseCase,
    RankArchiveUseCase,
    TauMeasurementEvidenceUseCase,
)
from nsqd.composition import build_container, build_local_ollama_embedder
from nsqd.domain.coverage import RankGuardBlocked
from nsqd.domain.diverge import enabled_operators_from_settings
from nsqd.domain.harvest import HarvestRejected
from nsqd.domain.novelty import novelty_threshold_tau_from_settings
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.domain.status import STATUS_WINDOW_DAYS
from nsqd.domain.tau_review import autonomous_tau_review_packet_digest
from nsqd.harvest import run_harvest
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.ports import ParaphraseEmbedder
from nsqd.project_runtime import load_verified_projection, run_project
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton
from papers.config.settings import (
    DEFAULT_OLLAMA_BASE_URL,
    Settings,
    packaged_defaults_path,
    public_configuration_error_message,
)
from papers.domain.errors import ConfigurationError, PipelineError
from papers.infra.llm_codex_subscription.client import CodexSubscriptionClient, RoutedLLMClient
from papers.infra.llm_openai_compat.client import build_openai_compat_client
from papers.infra.piccolo.database import PiccoloDatabase

app = typer.Typer(add_completion=False, no_args_is_help=True)

DEFAULT_NSQD_DB = Path("data/nsqd/nsqd.sqlite")
DEFAULT_NSQD_INDEX = Path("data/nsqd/corpus.lancedb")
_cli_options: dict[str, Path | None] = {"config": None}


@app.callback()
def _root(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Settings override TOML"),
    ] = None,
) -> None:
    """NS/QD-inspired discovery commands."""

    _cli_options["config"] = config


def _standalone_settings(config: Path | None = None) -> Settings:
    from papers.config.settings import load_settings

    return load_settings(defaults_path=packaged_defaults_path(), override_path=config)


def _standalone_embedder(config: Path | None = None) -> ParaphraseEmbedder:
    settings = _standalone_settings(config)
    return build_local_ollama_embedder(settings.embeddings)


@app.command()
def skeleton(
    candidate_fixture: Annotated[
        Path,
        typer.Option("--candidate-fixture", exists=True, readable=True),
    ],
    axiom: Annotated[str, typer.Option("--axiom")],
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        result = run_skeleton(
            fixture_path=candidate_fixture,
            axiom=axiom,
            db_path=db,
            index_path=index,
        )
    except (ImportError, OSError, PipelineError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    decision = result["card"]["card_decision"]
    viability = result["viability"]
    archive_state = "archive_empty" if result["archive_empty"] else "archive_has_elite"
    typer.echo(f"{decision} viability={viability} {archive_state} snapshot={result['snapshot_id']}")


@app.command()
def harvest(
    file: Annotated[Path, typer.Option("--file", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        result = run_harvest(
            file_path=file,
            db_path=db,
            index_path=index,
            embedder=_standalone_embedder(_cli_options["config"]),
        )
    except HarvestRejected as exc:
        typer.echo(f"rejected: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (ImportError, OSError, PipelineError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    count = len(result["record_ids"])
    typer.echo(f"accepted {count} records")


@app.command()
def project(
    projection: Annotated[Path, typer.Option("--projection", exists=True, readable=True)],
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        result = run_project(
            projection_path=projection,
            manifest_path=manifest,
            db_path=db,
            index_path=index,
            embedder=_standalone_embedder(_cli_options["config"]),
        )
    except (ImportError, OSError, PipelineError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        "projected "
        f"record={result['record_id']} "
        f"created={result['created']} "
        f"snapshot={result['snapshot_id']}"
    )


def _container(db: Path, index: Path, config: Path | None = None) -> Any:
    resolved_config = config if config is not None else _cli_options["config"]
    settings = _standalone_settings(resolved_config)
    return build_container(
        db_path=db,
        index_path=index,
        embedder=_standalone_embedder(resolved_config),
        enabled_operators=enabled_operators_from_settings(settings),
        novelty_threshold_tau=novelty_threshold_tau_from_settings(settings),
    )


def _default_paper_runtime(
    *,
    config: Path | None,
    db: Path | None,
    index: Path | None,
    llm_base_url: str,
    llm_api_key: str | None,
    approved_projection_digests: frozenset[str] | None = None,
) -> Any:
    from nsqd.infra.paper_runtime import compose_default_runtime
    from papers.app.composition_root import build_container as build_papers

    loaded = _standalone_settings(config)
    papers = build_papers(loaded, llm_base_url=llm_base_url, llm_api_key=llm_api_key)
    data_root = Path(loaded.data.root)
    return compose_default_runtime(
        papers=papers,
        nsqd_db_path=db if db is not None else data_root / "nsqd" / "nsqd.sqlite",
        nsqd_index_path=(index if index is not None else data_root / "nsqd" / "corpus.lancedb"),
        llm_base_url=llm_base_url,
        approved_projection_digests=approved_projection_digests,
    )


def _fail(exc: Exception) -> NoReturn:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=1) from exc


def _fail_configuration(exc: ConfigurationError) -> NoReturn:
    typer.echo(f"error: {public_configuration_error_message(exc)}", err=True)
    raise typer.Exit(code=1) from exc


def _canonical_json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


MAX_AUTONOMOUS_TAU_PACKET_BYTES = 8 * 1024 * 1024


def _load_autonomous_tau_rows(inputs: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in inputs:
        if path.stat().st_size > MAX_AUTONOMOUS_TAU_PACKET_BYTES:
            raise ValueError(f"autonomous tau packet exceeds byte limit: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"autonomous tau packet must be an object: {path}")
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ValueError(f"autonomous tau packet rows are required: {path}")
        packet_rows: list[dict[str, object]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                raise ValueError(f"autonomous tau packet row must be an object: {path}")
            packet_rows.append({str(key): value for key, value in raw_row.items()})
        if payload.get("packet_digest") != autonomous_tau_review_packet_digest(packet_rows):
            raise ValueError(f"autonomous tau packet digest drift: {path}")
        rows.extend(packet_rows)
    return rows


def _build_autonomous_tau_use_case(
    *,
    db: Path,
    index: Path,
    config: Path | None,
) -> AutonomousTauLabelingUseCase:
    settings = _standalone_settings(config)
    container = _container(db, index, config)
    autonomous_tau = settings.nsqd.autonomous_tau
    evidence = TauMeasurementEvidenceUseCase(
        candidates=container.ctx.candidates,
        approved_projection_digests=container.ctx.approved_projection_digests,
    )
    openai_client = build_openai_compat_client(
        base_url=autonomous_tau.writer.base_url or DEFAULT_OLLAMA_BASE_URL,
        api_key=None,
    )
    adjudicator = getattr(autonomous_tau, "adjudicator", None)
    llm_client = RoutedLLMClient(
        default_client=openai_client,
        provider_clients={
            "codex_subscription": CodexSubscriptionClient(
                executable_path=str(getattr(adjudicator, "executable_path", "codex") or "codex"),
                default_reasoning_effort=str(
                    getattr(adjudicator, "reasoning_effort", "high") or "high"
                ),
            )
        },
    )
    return AutonomousTauLabelingUseCase(
        measurement_evidence=evidence,
        llm_client=llm_client,
        clock=container.clock,
        settings=autonomous_tau,
    )


def _draft_review_summary(drafts: object, *, show_drafts: bool) -> tuple[int, list[dict[str, Any]]]:
    if not isinstance(drafts, list):
        return 0, []
    items: list[dict[str, Any]] = []
    for raw_draft in drafts:
        if not isinstance(raw_draft, dict):
            continue
        draft = {str(key): value for key, value in raw_draft.items() if isinstance(key, str)}
        paper_id = draft.get("paper_id")
        source_paper_id = draft.get("source_paper_id")
        item: dict[str, Any] = {}
        if isinstance(paper_id, str) and paper_id.strip():
            item["paper_id"] = paper_id.strip()
        if isinstance(source_paper_id, str) and source_paper_id.strip():
            item["source_paper_id"] = source_paper_id.strip()
        if show_drafts:
            for key in ("paraphrase", "paraphrase_source", "review_status", "title"):
                value = draft.get(key)
                if isinstance(value, str) and value.strip():
                    item[key] = value
        if item:
            items.append(item)
    return len(items), items


@app.command("map")
def map_snapshot(
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    domain_policy_id: Annotated[str, typer.Option("--domain-policy-id")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")],
    window_days: Annotated[
        int,
        typer.Option(
            "--window-days",
            help="Status recency window in days (v1 24 months = 730; overridable)",
        ),
    ] = STATUS_WINDOW_DAYS,
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        container = _container(db, index)
        result = run_job(
            container,
            "map",
            {
                "snapshot_id": snapshot_id,
                "domain_policy_id": domain_policy_id,
                "snapshot_state": snapshot_state,
                "window_days": window_days,
            },
            container.clock.now(),
        )
    except (ImportError, OSError, PipelineError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)
    counts = Counter(str(status) for status in result["cell_statuses"].values())
    typer.echo(
        json.dumps(
            {
                "snapshot_id": result["snapshot_id"],
                "domain_policy_id": result["domain_policy_id"],
                "window_days": result.get("window_days"),
                "counts": dict(counts),
            }
        )
    )


@app.command()
def diverge(
    candidate_fixture: Annotated[
        Path,
        typer.Option("--candidate-fixture", exists=True, readable=True),
    ],
    axiom: Annotated[str, typer.Option("--axiom")],
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    domain_policy_id: Annotated[str, typer.Option("--domain-policy-id")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")] = "calibration",
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        payload = yaml.safe_load(candidate_fixture.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("candidate fixture must be a mapping")
        container = _container(db, index)
        now = container.clock.now()
        mapped = run_job(
            container,
            "map",
            {
                "snapshot_id": snapshot_id,
                "domain_policy_id": domain_policy_id,
                "snapshot_state": snapshot_state,
            },
            now,
        )
        result = run_job(
            container,
            "diverge",
            {
                "candidate": payload,
                "axiom": axiom,
                "generator_run_id": str(uuid.uuid4()),
                "cell_statuses": mapped["cell_statuses"],
            },
            now,
        )
    except (ImportError, OSError, PipelineError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)
    typer.echo(f"candidate={result['candidate_artifact_hash']}")


@app.command()
def ground(
    candidate_artifact_hash: Annotated[str, typer.Option("--candidate-artifact-hash")],
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    corpus_version: Annotated[int, typer.Option("--corpus-version")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")] = "calibration",
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        container = _container(db, index)
        result = run_job(
            container,
            "ground",
            {
                "candidate_artifact_hash": candidate_artifact_hash,
                "snapshot_id": snapshot_id,
                "corpus_version": corpus_version,
                "snapshot_state": snapshot_state,
            },
            container.clock.now(),
        )
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(
        json.dumps(
            {
                "grounding_class": result.get("grounding_class"),
                "snapshot_id": snapshot_id,
            }
        )
    )


@app.command("export-tau-measurements")
def export_tau_measurements(
    candidate_artifact_hashes: Annotated[list[str], typer.Option("--candidate-artifact-hash")],
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        container = _container(db, index)
        payload = TauMeasurementEvidenceUseCase(
            candidates=container.ctx.candidates,
            approved_projection_digests=container.ctx.approved_projection_digests,
        ).export_jsonl(candidate_artifact_hashes)
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(payload.decode("utf-8"), nl=False)


@app.command("tau-measurement-inventory")
def tau_measurement_inventory(
    candidate_artifact_hashes: Annotated[list[str], typer.Option("--candidate-artifact-hash")],
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        container = _container(db, index)
        inventory = TauMeasurementEvidenceUseCase(
            candidates=container.ctx.candidates,
            approved_projection_digests=container.ctx.approved_projection_digests,
        ).inventory(candidate_artifact_hashes)
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(json.dumps(inventory, sort_keys=True))


@app.command("autonomous-tau-review")
def autonomous_tau_review(
    candidate_artifact_hashes: Annotated[list[str], typer.Option("--candidate-artifact-hash")],
    output: Annotated[Path, typer.Option("--output")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        result = _build_autonomous_tau_use_case(db=db, index=index, config=config).run(
            candidate_artifact_hashes
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_canonical_json_text(result), encoding="utf-8")
    except ConfigurationError as exc:
        _fail_configuration(exc)
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(
        json.dumps(
            {
                "approved_pair_count": result["packet"]["approved_pair_count"],
                "ambiguous_pair_count": result["packet"]["ambiguous_pair_count"],
                "output": str(output),
                "packet_digest": result["packet_digest"],
            },
            sort_keys=True,
        )
    )


@app.command("evaluate-autonomous-tau-reviews")
def evaluate_autonomous_tau_reviews(
    candidate_artifact_hashes: Annotated[list[str], typer.Option("--candidate-artifact-hash")],
    inputs: Annotated[list[Path], typer.Option("--input")],
    output: Annotated[Path, typer.Option("--output")],
    require_balanced: Annotated[bool, typer.Option("--require-balanced")] = False,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        settings = _standalone_settings(config)
        container = _container(db, index, config)
        evidence = TauMeasurementEvidenceUseCase(
            candidates=container.ctx.candidates,
            approved_projection_digests=container.ctx.approved_projection_digests,
        )
        result = AutonomousTauPacketEvaluationUseCase(
            measurement_evidence=evidence,
            audit_policy_revision=settings.nsqd.autonomous_tau.audit.policy_revision,
            audit_sample_rate=settings.nsqd.autonomous_tau.audit.sample_rate,
        ).run(
            candidate_artifact_hashes,
            _load_autonomous_tau_rows(inputs),
            require_balanced=require_balanced,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_canonical_json_text(result), encoding="utf-8")
    except ConfigurationError as exc:
        _fail_configuration(exc)
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(
        json.dumps(
            {
                "approved_pair_count": result["packet"]["approved_pair_count"],
                "ambiguous_pair_count": result["packet"]["ambiguous_pair_count"],
                "output": str(output),
                "packet_digest": result["packet_digest"],
            },
            sort_keys=True,
        )
    )


@app.command("gate")
def gate(
    candidate_artifact_hash: Annotated[str, typer.Option("--candidate-artifact-hash")],
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    corpus_version: Annotated[int, typer.Option("--corpus-version")],
    evaluator_run_id: Annotated[str, typer.Option("--evaluator-run-id")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")] = "calibration",
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        container = _container(db, index)
        result = run_job(
            container,
            "score",
            {
                "candidate_artifact_hash": candidate_artifact_hash,
                "snapshot_id": snapshot_id,
                "corpus_version": corpus_version,
                "evaluator_run_id": evaluator_run_id,
                "snapshot_state": snapshot_state,
            },
            container.clock.now(),
        )
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(
        f"{result['card_decision']} viability={result['viability']} cell={result['cell_id']}"
    )


@app.command()
def archive(
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    domain_policy_id: Annotated[str, typer.Option("--domain-policy-id")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")] = "calibration",
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    try:
        container = _container(db, index)
        mapped = run_job(
            container,
            "map",
            {
                "snapshot_id": snapshot_id,
                "domain_policy_id": domain_policy_id,
                "snapshot_state": snapshot_state,
            },
            container.clock.now(),
        )
        elites = container.ctx.cards.list_elites()
        policy_elites = [
            card for card in elites if str(card.get("domain_policy_id") or "") == domain_policy_id
        ]
        try:
            ranked = RankArchiveUseCase(
                cell_statuses=mapped["cell_statuses"],
                domain_policy_id=domain_policy_id,
            ).run(elite_cell_ids={str(card["cell_id"]) for card in policy_elites})
        except RankGuardBlocked as exc:
            ranked = {"allowed": False, "reason": str(exc)}
    except (
        ConfigurationError,
        ImportError,
        OSError,
        PipelineError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        _fail(exc)
    typer.echo(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "domain_policy_id": domain_policy_id,
                "elites": len(policy_elites),
                "rank": ranked,
            },
            default=str,
        )
    )


@app.command()
def acquire(
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    domain_policy_id: Annotated[str, typer.Option("--domain-policy-id")],
    target: Annotated[str, typer.Option("--target")] = "calibration",
    config: Annotated[Path | None, typer.Option("--config")] = None,
    db: Annotated[Path | None, typer.Option("--db")] = None,
    index: Annotated[Path | None, typer.Option("--index")] = None,
    llm_base_url: Annotated[str, typer.Option("--llm-base-url")] = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: Annotated[str | None, typer.Option("--llm-api-key")] = None,
    human_decision: Annotated[str | None, typer.Option("--human-decision")] = None,
    approved_projection: Annotated[
        list[Path] | None,
        typer.Option("--approved-projection", exists=True, readable=True),
    ] = None,
    approval_manifest: Annotated[
        Path | None,
        typer.Option("--approval-manifest", exists=True, readable=True),
    ] = None,
    show_drafts: Annotated[bool, typer.Option("--show-drafts")] = False,
) -> None:
    payload: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "domain_policy_id": domain_policy_id,
        "target": target,
    }
    if human_decision is not None:
        payload["human_decision"] = human_decision
    result: dict[str, Any] = {}
    approved_projection_digests: frozenset[str] | None = None
    try:
        if approved_projection:
            if approval_manifest is None:
                raise ValueError("--approval-manifest is required with --approved-projection")
            verified_projections = [
                load_verified_projection(
                    projection_path=path,
                    manifest_path=approval_manifest,
                )
                for path in approved_projection
            ]
            payload["approved_projections"] = verified_projections
            approved_projection_digests = frozenset(
                canonical_reviewed_projection_digest(projection)
                for projection in verified_projections
            )
        elif approval_manifest is not None:
            raise ValueError("--approved-projection is required with --approval-manifest")
        runtime = _default_paper_runtime(
            config=config,
            db=db,
            index=index,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            approved_projection_digests=approved_projection_digests,
        )
        result = run_job(runtime.nsqd, "acquire", payload, runtime.nsqd.clock.now())
    except ConfigurationError as exc:
        _fail_configuration(exc)
    except (ImportError, OSError, PipelineError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)
    draft_count, draft_items = _draft_review_summary(result.get("drafts"), show_drafts=show_drafts)
    typer.echo(
        json.dumps(
            {
                "stopped": result.get("stopped"),
                "route": result.get("route"),
                "projected": result.get("projected"),
                "snapshot_id": result.get("snapshot_id"),
                "draft_count": draft_count,
                "drafts": draft_items,
            },
            default=str,
        )
    )


@app.command("run-paper-jobs")
def run_paper_jobs(
    max_jobs: Annotated[int, typer.Option("--max-jobs", min=1)] = 1,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    llm_base_url: Annotated[str, typer.Option("--llm-base-url")] = DEFAULT_OLLAMA_BASE_URL,
    llm_api_key: Annotated[str | None, typer.Option("--llm-api-key")] = None,
) -> None:
    ran = 0
    try:
        runtime = _default_paper_runtime(
            config=config,
            db=None,
            index=None,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
        )
        for _ in range(max_jobs):
            if not runtime.paper_runner.run_next(runtime.nsqd.clock.now()):
                break
            ran += 1
    except ConfigurationError as exc:
        _fail_configuration(exc)
    except (ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"processed {ran} paper jobs")


@app.command("approve-digest")
def approve_digest(
    digest: Annotated[str, typer.Option("--digest")],
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_NSQD_DB,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_NSQD_INDEX,
) -> None:
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        _fail(ValueError("digest must be a lowercase SHA-256 hex digest"))
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        database = PiccoloDatabase(db)
        database.initialize_schema()
        digest_store = PiccoloApprovedDigestStore(database)
        digest_store.add(digest, approved_at=datetime.now(UTC))
    except (ConfigurationError, ImportError, OSError, PipelineError, ValueError) as exc:
        _fail(exc)
    if digest not in digest_store.list_digests():
        _fail(ValueError("approved digest was not persisted"))
    typer.echo(f"approved {digest}")


def main() -> None:
    app()
