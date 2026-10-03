from __future__ import annotations

from collections.abc import Mapping

from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from gleansight.api import Failure, GleansightAPI
from gleansight.api.models import ErrorData, Result


class ToolSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    namespaces: tuple[str, ...] = ()
    names: tuple[str, ...] = ()


class MCPAdapter:
    def __init__(self, api: GleansightAPI, selection: ToolSelection | None = None) -> None:
        self._api = api
        selection = selection or ToolSelection()
        catalog = api.operations()
        available = {operation.name for operation in catalog}
        unknown = set(selection.names) - available
        if unknown:
            raise ValueError(f"Unknown operations: {', '.join(sorted(unknown))}")
        self._operations = tuple(
            operation
            for operation in catalog
            if (not selection.names or operation.name in selection.names)
            and (
                not selection.namespaces
                or any(operation.name.startswith(prefix + ".") for prefix in selection.namespaces)
            )
        )
        self._names = frozenset(operation.name for operation in self._operations)

    def tools(self) -> list[Tool]:
        return [
            Tool(
                name=operation.name,
                description=operation.description,
                input_schema=operation.input_schema,
                annotations=ToolAnnotations(
                    read_only_hint=operation.effects == ("read",),
                    destructive_hint="write" in operation.effects,
                    idempotent_hint=operation.effects == ("read",),
                    open_world_hint="external" in operation.effects,
                ),
                meta={
                    "gleansight/effects": list(operation.effects),
                    "gleansight/requiresHumanApproval": operation.requires_human_approval,
                },
            )
            for operation in self._operations
        ]

    def call(self, name: str, arguments: Mapping[str, JsonValue]) -> CallToolResult:
        if name not in self._names:
            return self.error(name, "unknown_operation", f"Tool unavailable: {name}")
        return self._result(self._api.call(name, arguments))

    def error(self, name: str, code: str, message: str) -> CallToolResult:
        return self._result(Failure(operation=name, error=ErrorData(code=code, message=message)))

    @staticmethod
    def _result(envelope: Result) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=envelope.model_dump_json())],
            structured_content=TypeAdapter(dict[str, JsonValue]).validate_python(
                envelope.model_dump(mode="json")
            ),
            is_error=isinstance(envelope, Failure),
        )
