from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.shared.message import SessionMessage
from mcp.types import CallToolResult
from pydantic import JsonValue

from gleansight.api import GleansightAPI
from gleansight.api.models import EmptyRequest
from gleansight.api.operation import Operation
from gleansight.api.runtime import ApiRuntime
from gleansight.mcp import server


def answer(_runtime: ApiRuntime, _request: EmptyRequest) -> JsonValue:
    return {"answer": 42}


@pytest.mark.asyncio
async def test_server_lifecycle_with_real_client_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    to_server, server_read = anyio.create_memory_object_stream[SessionMessage](8)
    to_client, client_read = anyio.create_memory_object_stream[SessionMessage](8)

    @asynccontextmanager
    async def memory_stdio() -> AsyncIterator[
        tuple[MemoryObjectReceiveStream[SessionMessage], MemoryObjectSendStream[SessionMessage]]
    ]:
        async with server_read, to_client:
            yield server_read, to_client

    monkeypatch.setattr(server, "stdio_server", memory_stdio)
    api = GleansightAPI(
        operations=(Operation("fixture.answer", "Answer fixture", EmptyRequest, answer),)
    )
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(server.serve, api)
        async with ClientSession(client_read, to_server) as client:
            await client.initialize()
            catalog = await client.list_tools()
            assert [tool.name for tool in catalog.tools] == ["fixture.answer"]
            result = await client.call_tool("fixture.answer", {})
            assert isinstance(result, CallToolResult)
            assert result.is_error is False
            assert result.structured_content["data"] == {"answer": 42}
            invalid = await client.call_tool("fixture.answer", {"extra": "value"})
            assert isinstance(invalid, CallToolResult)
            assert invalid.is_error
        tasks.cancel_scope.cancel()
