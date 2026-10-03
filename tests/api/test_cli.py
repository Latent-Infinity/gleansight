from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gleansight.cli import app

runner = CliRunner()


def test_catalog_json_does_not_initialize_storage(tmp_path: Path) -> None:
    result = runner.invoke(app, ["api", "--repo-root", str(tmp_path), "operations"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["api_version"] == "1"
    assert any(row["name"] == "papers.candidates.list" for row in payload["data"])
    assert any(row["name"].startswith("nsqd.") for row in payload["data"])
    assert not list(tmp_path.iterdir())


def test_describe_approval_in_schema(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["api", "--repo-root", str(tmp_path), "describe", "nsqd.digests.approve"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["requires_human_approval"] is True
    assert not list(tmp_path.iterdir())


def test_invalid_input_emits_single_failure_without_storage(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "api",
            "--repo-root",
            str(tmp_path),
            "call",
            "papers.candidates.list",
            "--input-json",
            "[]",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "invalid_request"
    assert not list(tmp_path.iterdir())


def test_unknown_operation_is_json(tmp_path: Path) -> None:
    result = runner.invoke(app, ["api", "--repo-root", str(tmp_path), "call", "unknown"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "unknown_operation"


def test_stdin_input_is_supported(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "api",
            "--repo-root",
            str(tmp_path),
            "call",
            "papers.candidates.list",
            "--input-file",
            "-",
        ],
        input="{}",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ok"
