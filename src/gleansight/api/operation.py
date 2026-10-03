from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, assert_never

from pydantic import JsonValue, TypeAdapter

from gleansight.api.models import Effect, OperationDescription, Request
from gleansight.api.runtime import ApiRuntime

type JsonInput = (
    str
    | int
    | float
    | bool
    | None
    | date
    | datetime
    | Decimal
    | Path
    | Sequence[JsonInput]
    | Mapping[str, JsonInput]
)


class RegisteredOperation(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def effects(self) -> tuple[Effect, ...]: ...

    def describe(self) -> OperationDescription: ...
    def invoke(self, runtime: ApiRuntime, parameters: Mapping[str, JsonValue]) -> JsonValue: ...


@dataclass(frozen=True, slots=True)
class Operation[T: Request]:
    name: str
    description: str
    request_type: type[T]
    handler: Callable[[ApiRuntime, T], JsonValue]
    effects: tuple[Effect, ...] = ("read",)

    def describe(self) -> OperationDescription:
        return OperationDescription(
            name=self.name,
            description=self.description,
            effects=self.effects,
            input_schema=TypeAdapter(dict[str, JsonValue]).validate_python(
                self.request_type.model_json_schema()
            ),
            requires_human_approval="approval" in self.effects,
        )

    def invoke(self, runtime: ApiRuntime, parameters: Mapping[str, JsonValue]) -> JsonValue:
        request = self.request_type.model_validate_json(
            json.dumps(dict(parameters), allow_nan=False)
        )
        if "approval" in self.effects:
            runtime.require_approval()
        return self.handler(runtime, request)


def _json_default(value: date | datetime | Decimal | Path) -> str | float:
    match value:
        case date():
            return value.isoformat()
        case Path():
            return str(value)
        case Decimal():
            return float(value)
        case unreachable:
            assert_never(unreachable)


def json_result(value: JsonInput) -> JsonValue:
    """Normalize existing application results without accepting arbitrary object reprs."""
    return TypeAdapter(JsonValue).validate_json(
        json.dumps(value, default=_json_default, allow_nan=False)
    )
