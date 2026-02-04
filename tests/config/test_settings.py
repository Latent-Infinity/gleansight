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

[scholar]
api_key = ""
rate_limit_per_second = 1

[ui]
search_max_results = 10
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


def test_load_settings_scholar_config(tmp_path: Path) -> None:
    """Test that scholar config is loaded correctly."""
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)

    settings = load_settings(defaults_path=defaults_path, base_dir=tmp_path)

    assert settings.scholar.api_key == ""
    assert settings.scholar.rate_limit_per_second == 1

    # Test with API key override
    override_path = tmp_path / "override.toml"
    override_path.write_text(
        """
[scholar]
api_key = "test_key_123"
rate_limit_per_second = 100
""".strip()
    )

    settings = load_settings(
        defaults_path=defaults_path,
        override_path=override_path,
        base_dir=tmp_path,
    )

    assert settings.scholar.api_key == "test_key_123"
    assert settings.scholar.rate_limit_per_second == 100


def test_scholar_api_key_from_env_overrides_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variable should override config file value."""
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)

    # Override TOML has a key
    override_path = tmp_path / "override.toml"
    override_path.write_text(
        """
[scholar]
api_key = "from_config"
""".strip()
    )

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "from_env")

    settings = load_settings(
        defaults_path=defaults_path,
        override_path=override_path,
        base_dir=tmp_path,
    )

    assert settings.scholar.api_key == "from_env"


def test_scholar_api_key_from_env_when_config_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variable should be used when config value is empty."""
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "from_env_only")

    settings = load_settings(defaults_path=defaults_path, base_dir=tmp_path)

    assert settings.scholar.api_key == "from_env_only"


def test_scholar_api_key_uses_config_when_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config value should be used when environment variable is not set."""
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)

    override_path = tmp_path / "override.toml"
    override_path.write_text(
        """
[scholar]
api_key = "from_config_only"
""".strip()
    )

    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)

    settings = load_settings(
        defaults_path=defaults_path,
        override_path=override_path,
        base_dir=tmp_path,
    )

    assert settings.scholar.api_key == "from_config_only"
