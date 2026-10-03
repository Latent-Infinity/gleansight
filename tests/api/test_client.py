from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import Field, JsonValue

from gleansight.api.client import GleansightAPI
from gleansight.api.models import EmptyRequest, Failure, OperationError, Request, Success
from gleansight.api.operation import Operation
from gleansight.api.runtime import ApiConfiguration, ApiRuntime


class CountRequest(Request):
    count: int = Field(ge=1, le=10)


def _count(runtime: ApiRuntime, request: CountRequest) -> JsonValue:
    return {"count": request.count, "root": str(runtime.repo_root)}


def _failure(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    raise OperationError("not_found", "The requested resource does not exist.")


def test_discovery_does_not_load_configuration_or_create_data(tmp_path: Path) -> None:
    client = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path, config_path=Path("missing.toml")),
        operations=(Operation("test.count", "Count items.", CountRequest, _count),),
    )
    descriptions = client.operations()
    assert [item.name for item in descriptions] == ["test.count"]
    schema = client.describe("test.count").input_schema
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["count"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "parameters",
    [{"count": True}, {"count": 0}, {"count": 11}, {"count": "2"}, {"count": 1, "extra": 3}, {}],
)
def test_invalid_requests_fail_before_composition(
    tmp_path: Path, parameters: dict[str, JsonValue]
) -> None:
    client = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path, config_path=Path("missing.toml")),
        operations=(Operation("test.count", "Count items.", CountRequest, _count),),
    )
    result = client.call("test.count", parameters)
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"
    assert result.error.details
    assert not list(tmp_path.iterdir())


def test_valid_request_and_unknown_operation_return_versioned_envelopes(tmp_path: Path) -> None:
    client = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path),
        operations=(Operation("test.count", "Count items.", CountRequest, _count),),
    )
    success = client.call("test.count", {"count": 2})
    assert isinstance(success, Success)
    assert success.api_version == "1"
    assert success.data == {"count": 2, "root": str(tmp_path)}
    failure = client.call("missing", {})
    assert isinstance(failure, Failure)
    assert failure.error.code == "unknown_operation"
    assert failure.error.retryable is False


def test_business_error_preserves_code_without_becoming_success(tmp_path: Path) -> None:
    client = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path),
        operations=(Operation("test.missing", "Find a resource.", EmptyRequest, _failure),),
    )
    result = client.call("test.missing", {})
    assert isinstance(result, Failure)
    assert result.error.code == "not_found"


def test_authority_change_requires_explicit_separate_authorization(tmp_path: Path) -> None:
    client = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path),
        operations=(Operation("test.approval", "Approve.", CountRequest, _count, ("approval",)),),
    )
    result = client.call("test.approval", {"count": 1})
    assert isinstance(result, Failure)
    assert result.error.code == "approval_required"
    assert not list(tmp_path.iterdir())
