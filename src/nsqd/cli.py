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
from nsqd.harvest import run_harvest
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.project_runtime import run_project
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton
from papers.domain.errors import ConfigurationError
from papers.infra.piccolo.database import PiccoloDatabase

app = typer.Typer(add_completion=False, no_args_is_help=True)


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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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


def _fail(exc: Exception) -> NoReturn:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=1) from exc


@app.command("map")
def map_snapshot(
    snapshot_id: Annotated[str, typer.Option("--snapshot-id")],
    domain_policy_id: Annotated[str, typer.Option("--domain-policy-id")],
    snapshot_state: Annotated[str, typer.Option("--snapshot-state")],
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
    except (ImportError, OSError, ValueError, yaml.YAMLError) as exc:
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


@app.command("approve-digest")
def approve_digest(
    digest: Annotated[str, typer.Option("--digest")],
    db: Annotated[Path, typer.Option("--db")] = Path("data/nsqd/nsqd.sqlite"),
    index: Annotated[Path, typer.Option("--index")] = Path("data/nsqd/corpus.lancedb"),
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
