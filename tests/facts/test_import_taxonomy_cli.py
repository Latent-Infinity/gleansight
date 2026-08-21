from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from typer.testing import CliRunner


@dataclass
class FakeImport:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def import_candidate(
        self,
        candidate_id: str,
        *,
        project_ids: list[str] | None = None,
        tag_ids: list[str] | None = None,
    ) -> str:
        self.calls.append(
            {
                "candidate_id": candidate_id,
                "project_ids": project_ids or [],
                "tag_ids": tag_ids or [],
            }
        )
        return "paper-1"


@dataclass
class FakeContainer:
    import_candidate: FakeImport


def test_import_cli_forwards_repeatable_project_and_tag(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake = FakeImport()
    monkeypatch.setattr(cli_app, "get_container", lambda: FakeContainer(import_candidate=fake))
    runner = CliRunner()
    result = runner.invoke(
        cli_app.app,
        ["import", "cand-1", "--project", "p1", "--project", "p2", "--tag", "t1"],
    )
    assert result.exit_code == 0, result.output
    assert fake.calls == [
        {"candidate_id": "cand-1", "project_ids": ["p1", "p2"], "tag_ids": ["t1"]}
    ]


def test_import_help_lists_project_and_tag_flags() -> None:
    cli_app = importlib.import_module("papers.cli.app")
    result = CliRunner().invoke(cli_app.app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output
    assert "--tag" in result.output
