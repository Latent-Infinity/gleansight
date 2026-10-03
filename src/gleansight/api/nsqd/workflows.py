"""Adapters for existing NSQD business workflows."""

from pathlib import Path
from uuid import uuid4

import yaml
from pydantic import JsonValue, TypeAdapter

from gleansight.api.models import OperationError
from gleansight.api.nsqd.requests import (
    DivergeRequest,
    GateRequest,
    GroundRequest,
    HarvestRequest,
    MapRequest,
    ProjectRequest,
    RescoreRequest,
    SkeletonRequest,
)
from gleansight.api.operation import json_result
from gleansight.api.runtime import ApiRuntime
from nsqd.app.use_cases import RankArchiveUseCase
from nsqd.domain.coverage import RankGuardBlocked
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.domain.status import CellStatus
from nsqd.harvest import parse_harvest_file
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.project_runtime import load_verified_projection
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton


def bounded_input(runtime: ApiRuntime, path: Path) -> Path:
    """Bound file reads before passing inputs to the existing domain parser."""
    resolved = runtime.resolve(path)
    if resolved.stat().st_size > 8 * 1024 * 1024:
        raise OperationError("invalid_input", "Input exceeds the 8 MiB file limit")
    return resolved


def skeleton(runtime: ApiRuntime, request: SkeletonRequest) -> JsonValue:
    result = run_skeleton(
        fixture_path=bounded_input(runtime, request.candidate_fixture),
        axiom=request.axiom,
        db_path=runtime.nsqd_db,
        index_path=runtime.nsqd_index,
    )
    result["job_types"] = sorted(result["job_types"])
    return json_result(result)


def harvest(runtime: ApiRuntime, request: HarvestRequest) -> JsonValue:
    payload = parse_harvest_file(bounded_input(runtime, request.file))
    container = runtime.nsqd
    return json_result(run_job(container, "harvest", {"payload": payload}, container.clock.now()))


def project(runtime: ApiRuntime, request: ProjectRequest) -> JsonValue:
    projection = load_verified_projection(
        projection_path=bounded_input(runtime, request.projection),
        manifest_path=bounded_input(runtime, request.manifest),
    )
    container = runtime.nsqd
    digests = PiccoloApprovedDigestStore(container.database)
    digests.add(canonical_reviewed_projection_digest(projection), approved_at=container.clock.now())
    container.ctx.approved_projection_digests = digests.list_digests()
    return json_result(
        run_job(
            container,
            "project",
            {
                "projection": projection,
                "domain_policy_id": str(projection.get("domain_policy_id") or ""),
            },
            container.clock.now(),
        )
    )


def map_snapshot(runtime: ApiRuntime, request: MapRequest) -> JsonValue:
    container = runtime.nsqd
    return json_result(
        run_job(container, "map", request.model_dump(mode="json"), container.clock.now())
    )


def diverge(runtime: ApiRuntime, request: DivergeRequest) -> JsonValue:
    candidate = TypeAdapter(dict[str, JsonValue]).validate_python(
        yaml.safe_load(
            bounded_input(runtime, request.candidate_fixture).read_text(encoding="utf-8")
        )
    )
    container = runtime.nsqd
    if request.operator not in container.ctx.enabled_operators:
        raise OperationError("operator_disabled", f"Operator {request.operator} is not enabled")
    mapped = run_job(
        container,
        "map",
        {
            "snapshot_id": request.snapshot_id,
            "domain_policy_id": request.domain_policy_id,
            "snapshot_state": request.snapshot_state,
            "window_days": request.window_days,
        },
        container.clock.now(),
    )
    payload: dict[str, JsonValue] = {
        "candidate": candidate,
        "axiom": request.axiom,
        "operator": request.operator,
        "generator_run_id": str(uuid4()),
        "cell_statuses": mapped["cell_statuses"],
    }
    if request.target_cell_id is not None:
        payload["target_cell_id"] = request.target_cell_id
    if request.axiom_cell_id is not None:
        payload["axioms"] = [{"statement": request.axiom, "cell_id": request.axiom_cell_id}]
    return json_result(run_job(container, "diverge", payload, container.clock.now()))


def ground(runtime: ApiRuntime, request: GroundRequest) -> JsonValue:
    container = runtime.nsqd
    return json_result(
        run_job(container, "ground", request.model_dump(mode="json"), container.clock.now())
    )


def gate(runtime: ApiRuntime, request: GateRequest) -> JsonValue:
    container = runtime.nsqd
    return json_result(
        run_job(container, "score", request.model_dump(mode="json"), container.clock.now())
    )


def rescore(runtime: ApiRuntime, request: RescoreRequest) -> JsonValue:
    container = runtime.nsqd
    return json_result(
        run_job(container, "rescore", request.model_dump(mode="json"), container.clock.now())
    )


def rank(runtime: ApiRuntime, request: MapRequest) -> JsonValue:
    mapped = TypeAdapter(dict[str, JsonValue]).validate_python(map_snapshot(runtime, request))
    statuses = TypeAdapter(dict[str, CellStatus]).validate_python(mapped["cell_statuses"])
    elites = [
        card
        for card in runtime.nsqd.ctx.cards.list_elites()
        if card.get("domain_policy_id") == request.domain_policy_id
    ]
    try:
        ranked = RankArchiveUseCase(statuses, request.domain_policy_id).run(
            elite_cell_ids={str(card["cell_id"]) for card in elites},
        )
    except RankGuardBlocked as exc:
        ranked = {"allowed": False, "reason": str(exc)}
    return json_result(
        {
            "snapshot_id": request.snapshot_id,
            "domain_policy_id": request.domain_policy_id,
            "elites": TypeAdapter(JsonValue).validate_python(elites),
            "rank": TypeAdapter(JsonValue).validate_python(ranked),
            "cell_statuses": mapped["cell_statuses"],
        }
    )
