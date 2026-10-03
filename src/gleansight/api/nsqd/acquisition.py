"""Paper acquisition and explicit approval adapters."""

from pydantic import JsonValue, TypeAdapter

from gleansight.api.models import EmptyRequest
from gleansight.api.nsqd.requests import AcquireRequest, DigestRequest
from gleansight.api.nsqd.workflows import bounded_input
from gleansight.api.operation import json_result
from gleansight.api.runtime import ApiRuntime
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.infra.paper_runtime import compose_default_runtime
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.project_runtime import load_verified_projection
from nsqd.runner import run_job


def acquire(runtime: ApiRuntime, request: AcquireRequest) -> JsonValue:
    projections = []
    if request.approval_manifest is not None:
        manifest = bounded_input(runtime, request.approval_manifest)
        projections = [
            load_verified_projection(
                projection_path=bounded_input(runtime, path),
                manifest_path=manifest,
            )
            for path in request.approved_projections
        ]
    configured = compose_default_runtime(
        papers=runtime.papers,
        nsqd_db_path=runtime.nsqd_db,
        nsqd_index_path=runtime.nsqd_index,
        llm_base_url=runtime.configuration.llm_base_url,
        approved_projection_digests=frozenset(
            canonical_reviewed_projection_digest(projection) for projection in projections
        ),
    )
    payload = request.model_dump(
        mode="json", exclude={"approval_manifest", "approved_projections"}, exclude_none=True
    )
    if projections:
        payload["approved_projections"] = projections
    return json_result(run_job(configured.nsqd, "acquire", payload, configured.nsqd.clock.now()))


def approve_digest(runtime: ApiRuntime, request: DigestRequest) -> JsonValue:
    container = runtime.nsqd
    store = PiccoloApprovedDigestStore(container.database)
    store.add(request.digest, approved_at=container.clock.now())
    container.ctx.approved_projection_digests = store.list_digests()
    return {"digest": request.digest, "approved": request.digest in store.list_digests()}


def approved_digests(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    return TypeAdapter(JsonValue).validate_python(
        {"digests": sorted(PiccoloApprovedDigestStore(runtime.nsqd.database).list_digests())}
    )
