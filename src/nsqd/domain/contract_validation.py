from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import TypeGuard, assert_never

from nsqd.domain.contract_validation_errors import (
    ContractValidationError,
    ContractValidationReason,
)
from nsqd.domain.snapshot import is_utc_datetime_or_iso

type StructuredScalar = str | int | float | bool | None
type StructuredValue = StructuredScalar | list[StructuredValue] | dict[str, StructuredValue]
type StructuredInput = StructuredValue | tuple[StructuredInput, ...] | Mapping[str, StructuredInput]


def as_mapping(value: StructuredInput, field: str) -> dict[str, StructuredInput]:
    if not _is_string_mapping(value):
        raise ContractValidationError(ContractValidationReason.STRING_KEYED_MAPPING, field)
    return {key: item for key, item in value.items()}


def _is_string_mapping(value: StructuredInput) -> TypeGuard[Mapping[str, StructuredInput]]:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def mutable_mapping(value: StructuredInput | None) -> dict[str, StructuredInput] | None:
    if _is_mutable_mapping(value):
        return value
    return None


def _is_mutable_mapping(
    value: StructuredInput | None,
) -> TypeGuard[dict[str, StructuredInput]]:
    return type(value) is dict and all(isinstance(key, str) for key in value)


def normalize_value(value: StructuredInput) -> StructuredValue:
    match value:
        case dict() | Mapping():
            return normalize_mapping(as_mapping(value, "structured value"))
        case list():
            return [normalize_value(item) for item in value]
        case tuple():
            return [normalize_value(item) for item in value]
        case str() | bool() | int() | float() | None:
            return value
        case unreachable:
            assert_never(unreachable)


def normalize_mapping(value: Mapping[str, StructuredInput]) -> dict[str, StructuredValue]:
    return {key: normalize_value(item) for key, item in value.items()}


def mapping_list(value: StructuredInput, field: str) -> list[dict[str, StructuredInput]]:
    if type(value) is not list or not value:
        raise ContractValidationError(ContractValidationReason.NON_EMPTY_LIST, field)
    return [as_mapping(item, field) for item in value]


def require_exact_fields(
    value: Mapping[str, StructuredInput], expected: frozenset[str], field: str
) -> None:
    if set(value) != expected:
        raise ContractValidationError(ContractValidationReason.FIELDS_MISMATCH, field)


def required_string(value: Mapping[str, StructuredInput], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise ContractValidationError(ContractValidationReason.REQUIRED_STRING, field)
    return item.strip()


def string_list(value: StructuredInput, field: str) -> list[str]:
    if type(value) is not list or not value:
        raise ContractValidationError(ContractValidationReason.NON_EMPTY_LIST, field)
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(items) != len(value) or len(items) != len(set(items)):
        raise ContractValidationError(ContractValidationReason.UNIQUE_NON_EMPTY_STRINGS, field)
    return items


def require_schema_version(value: StructuredInput, field: str) -> int:
    if type(value) is not int or value != 1:
        raise ContractValidationError(ContractValidationReason.INTEGER_ONE, field)
    return value


def utc_instant(value: StructuredInput, field: str) -> datetime:
    if not is_utc_datetime_or_iso(value) or not isinstance(value, str):
        raise ContractValidationError(ContractValidationReason.UTC_INSTANT, field)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_exact_string_set(
    value: StructuredInput, expected: frozenset[str], field: str
) -> list[str]:
    items = string_list(value, field)
    if set(items) != expected:
        raise ContractValidationError(ContractValidationReason.VALUE_SET_MISMATCH, field)
    return items


def finite_numeric_mapping(value: StructuredInput, field: str) -> dict[str, float | int]:
    measured = as_mapping(value, field)
    if not measured:
        raise ContractValidationError(ContractValidationReason.NON_EMPTY_MAPPING, field)
    if any(
        not key.strip()
        or isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for key, item in measured.items()
    ):
        raise ContractValidationError(ContractValidationReason.FINITE_NUMERIC_MAPPING, field)
    return {key: item for key, item in measured.items() if isinstance(item, (int, float))}


def sha256_list(value: StructuredInput, field: str) -> list[str]:
    items = string_list(value, field)
    if any(
        len(item) != 64 or any(char not in "0123456789abcdef" for char in item) for item in items
    ):
        raise ContractValidationError(ContractValidationReason.LOWERCASE_SHA256_LIST, field)
    return items


def sha256_string(value: StructuredInput, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ContractValidationError(ContractValidationReason.LOWERCASE_SHA256_LIST, field)
    return value
