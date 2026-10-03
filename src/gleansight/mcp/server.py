from __future__ import annotations

import asyncio
import sys
from contextlib import redirect_stdout

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
)
from pydantic import JsonValue, TypeAdapter, ValidationError

from gleansight.api import GleansightAPI
from gleansight.mcp.adapter import MCPAdapter, ToolSelection


def build_server(adapter: MCPAdapter) -> Server[None]:
    lock = asyncio.Lock()

    async def list_tools(
        _context: ServerRequestContext[None], _parameters: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=adapter.tools())

    async def call_tool(
        _context: ServerRequestContext[None], parameters: CallToolRequestParams
    ) -> CallToolResult:
        try:
            arguments = TypeAdapter(dict[str, JsonValue]).validate_python(
                parameters.arguments or {}
            )
        except ValidationError:
            return adapter.error(parameters.name, "invalid_request", "Tool arguments must be JSON.")
        async with lock:
            return await asyncio.to_thread(adapter.call, parameters.name, arguments)

    return Server[None](
        "gleansight",
        version="0.1.0",
        instructions="Local workflows. Authority-bearing operations require human approval.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve(api: GleansightAPI, selection: ToolSelection | None = None) -> None:
    server = build_server(MCPAdapter(api, selection))
    async with stdio_server() as (read, write):
        with redirect_stdout(sys.stderr):
            await server.run(read, write, server.create_initialization_options())
