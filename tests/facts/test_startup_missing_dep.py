from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest
from typer.testing import CliRunner

from papers.app.composition_root import validate_startup
from papers.config.settings import ConfigurationError, Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "data": {
                "root": tmp_path / "data",
                "db_path": tmp_path / "data" / "db.sqlite",
                "blobs_dir": tmp_path / "data" / "blobs",
                "blobs_pdf_dir": tmp_path / "data" / "blobs" / "pdf",
                "blobs_md_dir": tmp_path / "data" / "blobs" / "md",
                "blobs_analysis_dir": tmp_path / "data" / "blobs" / "analysis",
                "lancedb_dir": tmp_path / "data" / "lancedb",
            },
            "embeddings": {
                "model": "fake",
                "dimension": 1,
                "text_slice_strategy": "markdown_full",
            },
            "llm": {"default_profile": "default"},
            "scholar": {"api_key": "", "rate_limit_per_second": 10},
            "ui": {},
        }
    )


def test_startup_names_missing_required_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    original_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str):
        if name == "lancedb":
            return None
        return original_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    with pytest.raises(ConfigurationError, match="lancedb"):
        validate_startup(settings)


def test_cli_startup_failure_hides_secret_and_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    secret = "SECRET_TOKEN_123"
    monkeypatch.setattr(cli_app, "_container", None)

    def _fail_settings(**kwargs):
        raise ConfigurationError("Missing required dependency: lancedb")

    monkeypatch.setattr(cli_app, "load_settings", _fail_settings)
    result = CliRunner().invoke(
        cli_app.app,
        ["--llm-api-key", secret, "query", "papers"],
    )

    assert result.exit_code == 1
    assert "Missing required dependency: lancedb" in result.output
    assert secret not in result.output
    assert "Traceback" not in result.output
    assert str(Path.cwd()) not in result.output
