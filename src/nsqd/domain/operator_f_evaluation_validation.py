from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated

import pydantic

type JsonValue = (
    str | int | float | bool | None | list[JsonValue] | tuple[JsonValue, ...] | dict[str, JsonValue]
)


class OperatorFValidationError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _finite_float(value: JsonValue) -> float:
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise OperatorFValidationError("value must be a finite float")


def _nonnegative_float(value: JsonValue) -> float:
    checked = _finite_float(value)
    if checked < 0:
        raise OperatorFValidationError("value must be nonnegative")
    return checked


def _binary_integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value not in {0, 1}:
        raise OperatorFValidationError("rating must be integer zero or one")
    return value


def _utc_instant(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise OperatorFValidationError("value must be a valid UTC instant") from error
    return value


Sha256 = Annotated[pydantic.StrictStr, pydantic.Field(pattern=r"^[0-9a-f]{64}$")]
NonBlank = Annotated[pydantic.StrictStr, pydantic.Field(min_length=1, pattern=r"\S")]
UtcInstant = Annotated[
    pydantic.StrictStr,
    pydantic.Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
    pydantic.AfterValidator(_utc_instant),
]
FiniteFloat = Annotated[pydantic.StrictFloat, pydantic.BeforeValidator(_finite_float)]
NonnegativeFloat = Annotated[pydantic.StrictFloat, pydantic.BeforeValidator(_nonnegative_float)]
BinaryInteger = Annotated[pydantic.StrictInt, pydantic.BeforeValidator(_binary_integer)]
