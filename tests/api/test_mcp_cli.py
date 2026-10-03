from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gleansight.api import GleansightAPI
from gleansight.mcp import cli
from gleansight.mcp.adapter import ToolSelection


def test_cli_passes_workspace_and_selection_without_granting_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[ToolSelection | None] = []

    async def observe(api: GleansightAPI, selection: ToolSelection | None) -> None:
        assert api.call("nsqd.digests.approve", {"digest": "a" * 64}).status == "error"
        captured.append(selection)

    monkeypatch.setattr(cli, "serve", observe)
    result = CliRunner().invoke(
        cli.app,
        ["--repo-root", str(tmp_path), "--namespace", "papers", "--tool", "papers.papers.list"],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert captured == [ToolSelection(namespaces=("papers",), names=("papers.papers.list",))]


def test_invalid_tool_selection_has_stderr_error_and_no_protocol_noise(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli.app, ["--repo-root", str(tmp_path), "--tool", "typo.missing"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Unknown operations" in result.stderr
