from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from papers.app.composition_root import validate_startup
from papers.config.settings import ConfigurationError, Settings, load_settings


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


def test_validate_startup_creates_dirs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    # Dirs don't exist yet
    assert not settings.data.root.exists()
    validate_startup(settings)
    # validate_startup auto-creates missing directories
    assert settings.data.root.exists()
    assert settings.data.blobs_dir.exists()
    assert settings.data.blobs_pdf_dir.exists()
    assert settings.data.blobs_md_dir.exists()
    assert settings.data.blobs_analysis_dir.exists()
    assert settings.data.lancedb_dir.exists()


def test_validate_startup_dir_creation_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    original_mkdir = Path.mkdir

    def _failing_mkdir(self, *args, **kwargs):
        if "blobs" in str(self):
            raise OSError("Permission denied")
        return original_mkdir(self, *args, **kwargs)

    with patch.object(Path, "mkdir", _failing_mkdir):
        with pytest.raises(ConfigurationError, match="Unable to create required directory"):
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


def test_missing_required_fields_fail_fast(tmp_path: Path) -> None:
    defaults_path = tmp_path / "defaults.toml"
    defaults_path.write_text(
        """
[data]
root = "data"
db_path = "data/db.sqlite"
blobs_dir = "data/blobs"
blobs_pdf_dir = "data/blobs/pdf"
blobs_md_dir = "data/blobs/md"
blobs_analysis_dir = "data/blobs/analysis"
lancedb_dir = "data/lancedb"

[embeddings]
model = "qwen3-embedding:latest"
dimension = 4096

[llm]
default_profile = "default"

[scholar]
api_key = ""
rate_limit_per_second = 10

[ui]
search_max_results = 10
""".strip()
    )

    with pytest.raises(ConfigurationError):
        load_settings(defaults_path=defaults_path, base_dir=tmp_path)
