from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
import yaml

from nsqd.app.use_cases import RankArchiveUseCase
from nsqd.composition import build_container
from nsqd.domain.coverage import RankGuardBlocked
from nsqd.domain.harvest import HarvestRejected
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.harvest import run_harvest
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.project_runtime import load_verified_projection, run_project
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton
from papers.config.settings import public_configuration_error_message
from papers.domain.errors import ConfigurationError
from papers.infra.piccolo.database import PiccoloDatabase

app = typer.Typer(add_completion=False, no_args_is_help=True)

DEFAULT_NSQD_DB = Path("data/nsqd/nsqd.sqlite")
DEFAULT_NSQD_INDEX = Path("data/nsqd/corpus.lancedb")


@app.callback()
def _root() -> None:
    """NS/QD-inspired discovery commands."""


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
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
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
        result = run_harvest(file_path=file, db_path=db, index_path=index)
    except HarvestRejected as exc:
        typer.echo(f"rejected: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
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
        )
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        "projected "
        f"record={result['record_id']} "
        f"created={result['created']} "
        f"snapshot={result['snapshot_id']}"
    )


def _container(db: Path, index: Path) -> Any:
    return build_container(db_path=db, index_path=index)


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
    from papers.config import settings as paper_settings

    defaults_path = Path(paper_settings.__file__).resolve().parent / "defaults.toml"
    loaded = paper_settings.load_settings(defaults_path=defaults_path, override_path=config)
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


@app.command("map")
def map_snapshot(
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    domain_policy_id: Annotated[str, typer.Option("--domain-policy-id")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")],
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
            },
            container.clock.now(),
        )
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)
    counts = Counter(str(status) for status in result["cell_statuses"].values())
    typer.echo(
        json.dumps(
            {
                "snapshot_id": result["snapshot_id"],
                "domain_policy_id": result["domain_policy_id"],
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
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
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
    except (ImportError, OSError, ValueError) as exc:
        _fail(exc)
    typer.echo(
        json.dumps(
            {
                "grounding_class": result.get("grounding_class"),
                "snapshot_id": snapshot_id,
            }
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
    except (ImportError, OSError, ValueError) as exc:
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
    except (ConfigurationError, ImportError, OSError, ValueError, yaml.YAMLError) as exc:
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
    llm_base_url: Annotated[str, typer.Option("--llm-base-url")] = "http://localhost:8000",
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
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)
    typer.echo(
        json.dumps(
            {
                "stopped": result.get("stopped"),
                "route": result.get("route"),
                "projected": result.get("projected"),
                "snapshot_id": result.get("snapshot_id"),
            },
            default=str,
        )
    )


@app.command("run-paper-jobs")
def run_paper_jobs(
    max_jobs: Annotated[int, typer.Option("--max-jobs", min=1)] = 1,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    llm_base_url: Annotated[str, typer.Option("--llm-base-url")] = "http://localhost:8000",
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
    except (ImportError, OSError, ValueError) as exc:
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
    except (ConfigurationError, ImportError, OSError, ValueError) as exc:
        _fail(exc)
    if digest not in digest_store.list_digests():
        _fail(ValueError("approved digest was not persisted"))
    typer.echo(f"approved {digest}")


def main() -> None:
    app()
