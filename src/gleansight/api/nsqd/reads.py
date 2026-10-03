"""Bounded, parameterized read queries for the local NSQD stores."""

from dataclasses import dataclass

from pydantic import JsonValue, TypeAdapter

from gleansight.api.models import OperationError
from gleansight.api.nsqd.requests import GetRequest, PageRequest, VerdictRequest
from gleansight.api.operation import json_result
from gleansight.api.runtime import ApiRuntime


@dataclass(frozen=True, slots=True)
class ReadResource:
    table: str
    key: str

    def list(self, runtime: ApiRuntime, request: PageRequest) -> JsonValue:
        rows = runtime.nsqd.database.fetchall(
            f"SELECT * FROM {self.table} ORDER BY {self.key} LIMIT ? OFFSET ?",
            [request.limit, request.offset],
        )
        return {
            "items": [_decode(row) for row in rows],
            "limit": request.limit,
            "offset": request.offset,
        }

    def get(self, runtime: ApiRuntime, request: GetRequest) -> JsonValue:
        row = runtime.nsqd.database.fetchone(
            f"SELECT * FROM {self.table} WHERE {self.key} = ?",
            [request.id],
        )
        if row is None:
            raise OperationError("not_found", f"No {self.table} record for {request.id}")
        return _decode(row)


def _decode(row: dict[str, JsonValue]) -> JsonValue:
    result = row.copy()
    for key in tuple(result):
        value = result[key]
        if key.endswith("_json"):
            encoded = TypeAdapter(str).validate_python(value)
            result[key.removesuffix("_json")] = TypeAdapter(JsonValue).validate_json(encoded)
            del result[key]
    return json_result(result)


def snapshot_members(runtime: ApiRuntime, request: GetRequest) -> JsonValue:
    if runtime.nsqd.ctx.snapshots.get(request.id) is None:
        raise OperationError("not_found", f"No snapshot {request.id}")
    return {
        "snapshot_id": request.id,
        "record_ids": TypeAdapter(JsonValue).validate_python(
            runtime.nsqd.ctx.snapshots.record_ids(request.id)
        ),
    }


def verdict(runtime: ApiRuntime, request: VerdictRequest) -> JsonValue:
    store = runtime.nsqd.ctx.verdicts
    if store is None:
        raise OperationError("unavailable", "Policy verdict store is unavailable")
    found = store.get_verdict(
        snapshot_id=request.snapshot_id, domain_policy_id=request.domain_policy_id
    )
    if found is None:
        raise OperationError("not_found", "No verdict for the snapshot and policy")
    return json_result(found)


def elites(runtime: ApiRuntime, request: PageRequest) -> JsonValue:
    rows = runtime.nsqd.database.fetchall(
        "SELECT cards.* FROM nsqd_elites AS elites "
        "JOIN nsqd_frontier_cards AS cards ON cards.card_id = elites.card_id "
        "ORDER BY elites.cell_id LIMIT ? OFFSET ?",
        [request.limit, request.offset],
    )
    return {
        "items": [_decode(row) for row in rows],
        "limit": request.limit,
        "offset": request.offset,
    }


def cancel_job(runtime: ApiRuntime, request: GetRequest) -> JsonValue:
    resource = ReadResource("nsqd_jobs", "job_id")
    resource.get(runtime, request)
    runtime.nsqd.queue.cancel(request.id)
    return resource.get(runtime, request)
