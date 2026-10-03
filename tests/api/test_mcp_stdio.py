from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent
from pydantic import JsonValue, TypeAdapter


@pytest.mark.asyncio
async def test_official_client_invokes_real_registry_over_stdio(tmp_path: Path) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gleansight.mcp", "--repo-root", str(tmp_path), "--namespace", "papers"],
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            initialization = await client.initialize()
            assert initialization.protocol_version == "2025-11-25"
            catalog = await client.list_tools()
            assert catalog.tools
            assert all(tool.name.startswith("papers.") for tool in catalog.tools)
            result = await client.call_tool("papers.papers.list", {})
            assert isinstance(result, CallToolResult)
            assert result.is_error is False
            envelope = TypeAdapter(dict[str, JsonValue]).validate_python(result.structured_content)
            assert envelope["status"] == "ok"
            assert envelope["operation"] == "papers.papers.list"
            assert envelope["data"] == {"items": [], "next_offset": None}
            assert isinstance(result.content[0], TextContent)
            assert json.loads(result.content[0].text) == envelope
            invalid = await client.call_tool("papers.papers.list", {"limit": 0})
            assert isinstance(invalid, CallToolResult)
            assert invalid.is_error
            assert invalid.structured_content["error"]["code"] == "invalid_request"
            unavailable = await client.call_tool("nsqd.operators.list", {})
            assert isinstance(unavailable, CallToolResult)
            assert unavailable.is_error
            assert unavailable.structured_content["error"]["code"] == "unknown_operation"


@pytest.mark.asyncio
async def test_stdio_approval_requires_explicit_launch_authorization(tmp_path: Path) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "gleansight.mcp",
            "--repo-root",
            str(tmp_path),
            "--tool",
            "nsqd.digests.approve",
        ],
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            result = await client.call_tool("nsqd.digests.approve", {"digest": "a" * 64})
            assert isinstance(result, CallToolResult)
            assert result.is_error
            assert result.structured_content["error"]["code"] == "approval_required"
    assert not (tmp_path / "data" / "nsqd" / "nsqd.sqlite").exists()


@pytest.mark.asyncio
async def test_provider_prints_go_to_stderr_and_keep_stdio_parseable(tmp_path: Path) -> None:
    program = """
import asyncio
from gleansight.api import GleansightAPI
from gleansight.api.models import EmptyRequest
from gleansight.api.operation import Operation
from gleansight.api.runtime import ApiRuntime
from gleansight.mcp.server import serve
from pydantic import JsonValue
def noisy(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    print('provider diagnostic')
    return {'answer': 42}
asyncio.run(serve(GleansightAPI(operations=(
    Operation('fixture.noisy', 'Noise fixture', EmptyRequest, noisy),
))))
"""
    stderr_path = tmp_path / "stderr.log"
    parameters = StdioServerParameters(command=sys.executable, args=["-c", program])
    with stderr_path.open("w", encoding="utf-8") as stderr:
        async with stdio_client(parameters, errlog=stderr) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                result = await client.call_tool("fixture.noisy", {})
                assert isinstance(result, CallToolResult)
                assert result.is_error is False
                assert result.structured_content["data"] == {"answer": 42}
    assert "provider diagnostic" in stderr_path.read_text(encoding="utf-8")
