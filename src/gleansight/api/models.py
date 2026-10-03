from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints

type Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type Effect = Literal["read", "write", "external", "approval"]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EmptyRequest(Request):
    pass


class OperationDescription(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    effects: tuple[Effect, ...]
    input_schema: dict[str, JsonValue]
    requires_human_approval: bool = False


class ErrorDetail(BaseModel):
    location: tuple[str | int, ...]
    code: str
    message: str


class ErrorData(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: tuple[ErrorDetail, ...] = ()


class Success(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_version: Literal["1"] = "1"
    status: Literal["ok"] = "ok"
    operation: str
    data: JsonValue


class Failure(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_version: Literal["1"] = "1"
    status: Literal["error"] = "error"
    operation: str
    error: ErrorData


type Result = Success | Failure


class OperationError(RuntimeError):
    """An expected operation failure with a stable public error code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
