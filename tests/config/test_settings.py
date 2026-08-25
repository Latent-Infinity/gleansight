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
base_url = "http://127.0.0.1:11434"

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


def test_packaged_defaults_toml_loads() -> None:
    defaults_path = (
        Path(__file__).resolve().parents[2] / "src" / "papers" / "config" / "defaults.toml"
    )
    settings = load_settings(defaults_path=defaults_path)

    assert settings.embeddings.model == "qwen3-embedding:latest"
    assert settings.embeddings.dimension == 4096
    assert settings.llm.default_model == "qwen3.6:35b-a3b-q4_K_M"
    assert settings.data.db_path.name == "app.sqlite"
    assert settings.scholar.rate_limit_per_second == 1


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


def test_load_settings_scholar_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that scholar config is loaded correctly."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
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


@pytest.mark.parametrize(
    ("embedding_block", "message"),
    [
        (
            """
[embeddings]
model = "   "
dimension = 384
text_slice_strategy = "markdown_full"
base_url = "http://127.0.0.1:11434"
""".strip(),
            "model",
        ),
        (
            """
[embeddings]
model = "qwen3-embedding:latest"
dimension = 0
text_slice_strategy = "markdown_full"
base_url = "http://127.0.0.1:11434"
""".strip(),
            "dimension",
        ),
        (
            """
[embeddings]
model = "qwen3-embedding:latest"
dimension = 4096
text_slice_strategy = "   "
base_url = "http://127.0.0.1:11434"
""".strip(),
            "text_slice_strategy",
        ),
        (
            """
[embeddings]
model = "qwen3-embedding:latest"
dimension = 4096
text_slice_strategy = "markdown_full"
base_url = "ftp://127.0.0.1:11434"
""".strip(),
            "base_url",
        ),
    ],
)
def test_embedding_settings_validation_rejects_invalid_values(
    tmp_path: Path,
    embedding_block: str,
    message: str,
) -> None:
    defaults_path = tmp_path / "defaults.toml"
    defaults_path.write_text(
        "\n".join(
            [
                "[data]",
                'root = "data"',
                'db_path = "data/db.sqlite"',
                'blobs_dir = "data/blobs"',
                'blobs_pdf_dir = "data/blobs/pdf"',
                'blobs_md_dir = "data/blobs/md"',
                'blobs_analysis_dir = "data/blobs/analysis"',
                'lancedb_dir = "data/lancedb"',
                "",
                embedding_block,
                "",
                "[llm]",
                'default_profile = "default"',
                "",
                "[scholar]",
                'api_key = ""',
                "rate_limit_per_second = 1",
                "",
                "[ui]",
                "search_max_results = 10",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=message):
        load_settings(defaults_path=defaults_path, base_dir=tmp_path)


@pytest.mark.parametrize(
    ("llm_block", "message"),
    [
        (
            """
[llm]
default_profile = "   "
""".strip(),
            "default_profile",
        ),
        (
            """
[llm]
default_profile = "default"
default_model = "   "
""".strip(),
            "default_model",
        ),
    ],
)
def test_llm_settings_validation_rejects_blank_values(
    tmp_path: Path,
    llm_block: str,
    message: str,
) -> None:
    defaults_path = tmp_path / "defaults.toml"
    defaults_path.write_text(
        "\n".join(
            [
                "[data]",
                'root = "data"',
                'db_path = "data/db.sqlite"',
                'blobs_dir = "data/blobs"',
                'blobs_pdf_dir = "data/blobs/pdf"',
                'blobs_md_dir = "data/blobs/md"',
                'blobs_analysis_dir = "data/blobs/analysis"',
                'lancedb_dir = "data/lancedb"',
                "",
                "[embeddings]",
                'model = "qwen3-embedding:latest"',
                "dimension = 4096",
                'text_slice_strategy = "markdown_full"',
                'base_url = "http://127.0.0.1:11434"',
                "",
                llm_block,
                "",
                "[scholar]",
                'api_key = ""',
                "rate_limit_per_second = 1",
                "",
                "[ui]",
                "search_max_results = 10",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=message):
        load_settings(defaults_path=defaults_path, base_dir=tmp_path)
