from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True, slots=True)
class UnsupportedStructuredInput:
    value_type: str


@dataclass(frozen=True, slots=True)
class NonStringMappingInput:
    pass


@dataclass(frozen=True, slots=True)
class StructuredNestingLimitInput:
    depth: int


type StructuredInput = (
    str
    | int
    | float
    | bool
    | None
    | date
    | datetime
    | time
    | UnsupportedStructuredInput
    | NonStringMappingInput
    | StructuredNestingLimitInput
    | list[StructuredInput]
    | dict[str, StructuredInput]
)


def parse_structured_input[DecodedValue](
    value: DecodedValue,
    depth: int = 0,
    max_depth: int = 64,
) -> StructuredInput:
    if depth > max_depth:
        return StructuredNestingLimitInput(max_depth)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, list):
        return [parse_structured_input(item, depth + 1, max_depth) for item in value]
    if isinstance(value, dict):
        parsed: dict[str, StructuredInput] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return NonStringMappingInput()
            parsed[key] = parse_structured_input(item, depth + 1, max_depth)
        return parsed
    return UnsupportedStructuredInput(type(value).__name__)
