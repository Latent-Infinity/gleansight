from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import JsonValue

from gleansight.api import ApiConfiguration, GleansightAPI
from gleansight.api.models import EmptyRequest
from gleansight.api.operation import Operation
from gleansight.api.runtime import ApiRuntime
from gleansight.mcp.adapter import MCPAdapter, ToolSelection


def read_handler(_runtime: ApiRuntime, _request: EmptyRequest) -> JsonValue:
    return {"value": "local"}


@pytest.fixture
def api(tmp_path: Path) -> GleansightAPI:
    return GleansightAPI(
        ApiConfiguration(repo_root=tmp_path),
        operations=(
            Operation("papers.read", "Read fixture.", EmptyRequest, read_handler),
            Operation(
                "nsqd.approve",
                "Approve fixture.",
                EmptyRequest,
                read_handler,
                effects=("write", "approval"),
            ),
        ),
    )


def test_tool_catalog_uses_registry_schemas_and_effects(api: GleansightAPI) -> None:
    adapter = MCPAdapter(api)
    tools = {tool.name: tool for tool in adapter.tools()}
    assert tools.keys() == {"papers.read", "nsqd.approve"}
    read = tools["papers.read"].model_dump(by_alias=True)
    approval = tools["nsqd.approve"].model_dump(by_alias=True)
    assert read["inputSchema"] == api.describe("papers.read").input_schema
    assert read["annotations"]["readOnlyHint"] is True
    assert approval["annotations"]["readOnlyHint"] is False
    assert approval["_meta"]["gleansight/effects"] == ["write", "approval"]
    assert approval["_meta"]["gleansight/requiresHumanApproval"] is True


def test_selection_is_a_namespace_and_explicit_tool_intersection(api: GleansightAPI) -> None:
    adapter = MCPAdapter(api, ToolSelection(namespaces=("papers",)))
    assert [tool.name for tool in adapter.tools()] == ["papers.read"]
    restricted = MCPAdapter(api, ToolSelection(names=("papers.read",)))
    assert restricted.call("nsqd.approve", {}).is_error
    with pytest.raises(ValueError, match="Unknown"):
        MCPAdapter(api, ToolSelection(names=("papers.typo",)))


def test_success_and_error_envelopes_match_python_api(api: GleansightAPI) -> None:
    adapter = MCPAdapter(api)
    result = adapter.call("papers.read", {})
    assert result.is_error is False
    assert result.structured_content == api.call("papers.read", {}).model_dump(mode="json")
    invalid = adapter.call("papers.read", {"extra": True})
    assert invalid.is_error
    assert invalid.structured_content["error"]["code"] == "invalid_request"
    approval = adapter.call("nsqd.approve", {})
    assert approval.is_error
    assert approval.structured_content["error"]["code"] == "approval_required"
    unknown = adapter.call("papers.unknown", {})
    assert unknown.is_error
    assert unknown.structured_content["error"]["code"] == "unknown_operation"
