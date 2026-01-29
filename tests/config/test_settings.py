from __future__ import annotations

from pathlib import Path

import pytest

from papers.config.settings import load_settings
from papers.domain.errors import ConfigurationError


def _write_defaults(path: Path) -> None:
    path.write_text(
        """
[data]
root = "data"
db_path = "data/db/app.sqlite"
blobs_dir = "data/blobs"
blobs_pdf_dir = "data/blobs/pdf"
blobs_md_dir = "data/blobs/md"
blobs_analysis_dir = "data/blobs/analysis"
lancedb_dir = "data/lancedb"

[embeddings]
model = "sentence-transformers/all-MiniLM-L6-v2"
dimension = 384
text_slice_strategy = "markdown_full"

[llm]
default_profile = "default"
""".strip()
    )


def test_load_settings_resolves_paths(tmp_path: Path) -> None:
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)

    settings = load_settings(defaults_path=defaults_path, base_dir=tmp_path)

    assert settings.data.root == (tmp_path / "data").resolve()
    assert settings.data.db_path == (tmp_path / "data/db/app.sqlite").resolve()


def test_load_settings_missing_file_raises(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.toml"
    with pytest.raises(ConfigurationError):
        load_settings(defaults_path=missing_path, base_dir=tmp_path)


def test_load_settings_with_override(tmp_path: Path) -> None:
    defaults_path = tmp_path / "defaults.toml"
    override_path = tmp_path / "override.toml"
    _write_defaults(defaults_path)
    override_path.write_text(
        """
[embeddings]
model = "sentence-transformers/all-mpnet-base-v2"
""".strip()
    )

    settings = load_settings(
        defaults_path=defaults_path,
        override_path=override_path,
        base_dir=tmp_path,
    )

    assert settings.embeddings.model == "sentence-transformers/all-mpnet-base-v2"
