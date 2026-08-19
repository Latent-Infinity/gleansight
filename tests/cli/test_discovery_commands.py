from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from typer.testing import CliRunner


@dataclass
class FakeDiscover:
    calls: list[dict[str, Any]] = field(default_factory=list)
    raise_error: bool = False

    def discover(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int | None = None,
    ):
        self.calls.append(
            {
                "query": query,
                "filters": filters,
                "max_results": max_results,
                "page_size": page_size,
            }
        )
        if self.raise_error:
            raise RuntimeError("boom")
        return ["cand-1", "cand-2"]


@dataclass
class FakeImport:
    calls: list[str] = field(default_factory=list)
    raise_error: bool = False

    def import_candidate(self, candidate_id: str) -> str:
        if self.raise_error:
            raise RuntimeError("cannot import")
        self.calls.append(candidate_id)
        return "paper-1"


@dataclass
class FakeScholar:
    require_open_access: bool = False


@dataclass
class FakeSettings:
    scholar: FakeScholar = field(default_factory=FakeScholar)


@dataclass
class FakeContainer:
    discover: FakeDiscover
    import_candidate: FakeImport
    get_candidate: Any = None
    settings: FakeSettings = field(default_factory=FakeSettings)


def test_discover_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        discover=FakeDiscover(),
        import_candidate=FakeImport(),
        get_candidate=lambda cid: {
            "candidate_id": cid,
            "title": f"Title {cid}",
            "year": 2024,
            "venue": "NeurIPS",
        },
    )

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["discover", "transformer", "--max-results", "2"])

    assert result.exit_code == 0
    assert "Found 2 candidates" in result.output
    assert "Title cand-1" in result.output
    assert container.discover.calls[0]["query"] == "transformer"


def test_import_command(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        discover=FakeDiscover(), import_candidate=FakeImport(), get_candidate=None
    )

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(cli_app.app, ["import", "cand-1"])

    assert result.exit_code == 0
    assert "paper-1" in result.output
    assert container.import_candidate.calls == ["cand-1"]


def test_discover_with_year_filters(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        discover=FakeDiscover(), import_candidate=FakeImport(), get_candidate=None
    )

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        ["discover", "transformer", "--year-min", "2020", "--year-max", "2024"],
    )

    assert result.exit_code == 0
    assert "Found 2 candidates" in result.output
    assert container.discover.calls[0]["filters"] == {"year_min": 2020, "year_max": 2024}


def test_discover_with_extended_filters_and_page_size(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        discover=FakeDiscover(), import_candidate=FakeImport(), get_candidate=None
    )

    monkeypatch.setattr(cli_app, "get_container", lambda: container)

    result = runner.invoke(
        cli_app.app,
        [
            "discover",
            "transformer",
            "--max-results",
            "25",
            "--page-size",
            "10",
            "--publication-types",
            "Journal,Conference",
            "--fields-of-study",
            "Computer Science",
            "--venue",
            "NeurIPS",
            "--min-citation-count",
            "50",
            "--publication-date-or-year",
            "2020-01-01:2024-12-31",
        ],
    )

    assert result.exit_code == 0
    call = container.discover.calls[0]
    assert call["page_size"] == 10
    assert call["filters"]["publication_types"] == "Journal,Conference"
    assert call["filters"]["fields_of_study"] == "Computer Science"
    assert call["filters"]["venue"] == "NeurIPS"
    assert call["filters"]["min_citation_count"] == 50
    assert call["filters"]["publication_date_or_year"] == "2020-01-01:2024-12-31"


def test_discover_command_error_handling(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        discover=FakeDiscover(raise_error=True),
        import_candidate=FakeImport(),
        get_candidate=None,
    )

    monkeypatch.setattr(cli_app, "get_container", lambda: container)
    result = runner.invoke(cli_app.app, ["discover", "transformer"])

    assert result.exit_code == 1
    assert "Discover failed: boom" in result.output


def test_import_command_error_handling(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    runner = CliRunner()
    container = FakeContainer(
        discover=FakeDiscover(),
        import_candidate=FakeImport(raise_error=True),
        get_candidate=None,
    )

    monkeypatch.setattr(cli_app, "get_container", lambda: container)
    result = runner.invoke(cli_app.app, ["import", "cand-1"])

    assert result.exit_code == 1
    assert "Import failed for cand-1: cannot import" in result.output
