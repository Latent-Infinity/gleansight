from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import EmptyRequest
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime


def capabilities(runtime: ApiRuntime, _request: EmptyRequest) -> JsonValue:
    settings = runtime.settings
    return json_result(
        {
            "api_version": "1",
            "transports": ["python", "json_cli"],
            "repo_root": runtime.repo_root,
            "paper_database": settings.data.db_path,
            "nsqd_database": runtime.nsqd_db,
            "nsqd_index": runtime.nsqd_index,
            "enabled_operators": sorted(settings.nsqd.enabled_operators),
            "deferred_operators": ["C", "D", "F", "G"],
            "approval_operations_enabled": runtime.configuration.allow_approvals,
            "default_llm_profile": settings.llm.default_profile,
            "default_llm_model": settings.llm.default_model,
            "embedding_model": settings.embeddings.model,
            "embedding_dimension": settings.embeddings.dimension,
            "scholar_api_key_configured": bool(settings.scholar.api_key),
        }
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "system.capabilities",
            "Inspect resources, enabled operators, and provider metadata without startup.",
            EmptyRequest,
            capabilities,
        ),
    )
