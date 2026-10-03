from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import JsonValue
from typer.testing import CliRunner

from gleansight.api import ApiConfiguration, Failure, GleansightAPI
from gleansight.api.models import EmptyRequest
from gleansight.api.operation import Operation, json_result
from gleansight.api.runtime import ApiRuntime
from gleansight.cli import app
from papers.domain.errors import ConfigurationError


def test_result_normalization_preserves_native_storage_values() -> None:
    value = json_result(
        {
            "cost": Decimal("0.125"),
            "created": datetime(2026, 10, 2, tzinfo=UTC),
            "path": Path("output/report.json"),
            "ids": ("a", "b"),
        }
    )
    assert value == {
        "cost": 0.125,
        "created": "2026-10-02T00:00:00+00:00",
        "path": "output/report.json",
        "ids": ["a", "b"],
    }


def test_result_normalization_rejects_nonfinite_numbers() -> None:
    with pytest.raises(ValueError):
        json_result({"score": Decimal("NaN")})


@pytest.mark.parametrize("configuration_failure", [False, True])
def test_unexpected_and_configuration_errors_do_not_disclose_secrets(
    tmp_path: Path, configuration_failure: bool, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "hidden-provider-key-value"

    def handler(_runtime: ApiRuntime, _request: EmptyRequest) -> JsonValue:
        if configuration_failure:
            raise ConfigurationError(secret)
        raise RuntimeError(secret)

    api = GleansightAPI(
        ApiConfiguration(repo_root=tmp_path),
        operations=(
            Operation("test.failure", "Exercise public error isolation", EmptyRequest, handler),
        ),
    )
    result = api.call("test.failure", {})
    assert isinstance(result, Failure)
    assert secret not in result.model_dump_json()
    assert secret not in caplog.text
    assert result.error.code == (
        "configuration_error" if configuration_failure else "internal_error"
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("payload", ["{", "null", "[]", "1", '{"limit":true}'])
def test_malformed_json_or_schema_has_no_storage_side_effects(tmp_path: Path, payload: str) -> None:
    result = CliRunner().invoke(
        app,
        [
            "api",
            "--repo-root",
            str(tmp_path),
            "call",
            "papers.candidates.list",
            "--input-json",
            payload,
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid_request"
    assert not list(tmp_path.iterdir())


def test_request_file_and_conflicting_sources_are_bounded(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_bytes(b" " * (1024 * 1024 + 1))
    args = ["api", "--repo-root", str(tmp_path), "call", "papers.candidates.list"]
    runner = CliRunner()
    oversized = runner.invoke(app, [*args, "--input-file", str(request)])
    conflict = runner.invoke(app, [*args, "--input-json", "{}", "--input-file", str(request)])
    unreadable = runner.invoke(app, [*args, "--input-file", str(tmp_path / "missing")])
    assert oversized.exit_code == conflict.exit_code == 2
    assert unreadable.exit_code == 1
    assert json.loads(oversized.stdout)["error"]["code"] == "invalid_request"
    assert json.loads(conflict.stdout)["error"]["code"] == "invalid_request"
    assert json.loads(unreadable.stdout)["error"]["code"] == "io_error"
    assert list(tmp_path.iterdir()) == [request]
