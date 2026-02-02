from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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
        }
    )


def test_validate_startup_missing_dirs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(ConfigurationError, match="Missing required directory"):
        validate_startup(settings)


def test_validate_startup_missing_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    settings.data.root.mkdir(parents=True, exist_ok=True)
    settings.data.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.data.blobs_dir.mkdir(parents=True, exist_ok=True)
    settings.data.blobs_pdf_dir.mkdir(parents=True, exist_ok=True)
    settings.data.blobs_md_dir.mkdir(parents=True, exist_ok=True)
    settings.data.blobs_analysis_dir.mkdir(parents=True, exist_ok=True)
    settings.data.lancedb_dir.mkdir(parents=True, exist_ok=True)

    original_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str):
        if name == "lancedb":
            return None
        return original_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    with pytest.raises(ConfigurationError, match="lancedb"):
        validate_startup(settings)
