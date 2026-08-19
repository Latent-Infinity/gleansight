from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from papers.app import composition_root
from papers.config.settings import ConfigurationError, Settings, load_settings


class _FakeVectorIndex:
    def __init__(self, config):
        self.config = config

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []


class _FakeBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root


class _FakeConverter:
    def version(self) -> str:
        return "fake"

    def pdf_to_markdown(self, pdf_path: Path):
        raise AssertionError("not used")


class _FakeEmbedder:
    def model_name(self) -> str:
        return "fake"

    def dimension(self) -> int:
        return 1

    def embed(self, text: str) -> list[float]:
        return [0.0]


class _FakeLLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        raise AssertionError("not used")


class _FakeScholarClient:
    def search(self, query: str, filters: dict, max_results: int, page_size: int):
        raise AssertionError("not used")


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
            "ui": {"search_max_results": 10},
        }
    )


def test_build_container_wires_dependencies(
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

    def _fake_build_embedder(model_name: str):
        assert model_name == "fake"
        return _FakeEmbedder()

    def _fake_build_converter():
        return _FakeConverter()

    def _fake_build_llm_client(*, base_url: str, api_key: str | None = None):
        assert base_url == "http://local"
        assert api_key == "token"
        return _FakeLLM()

    def _fake_build_s2_client(*, api_key: str | None = None, rate_limit_per_second: int = 10):
        return _FakeScholarClient()

    original_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str):
        if name in {"docling", "lancedb", "sentence_transformers", "httpx"}:
            return object()
        return original_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    monkeypatch.setattr(composition_root, "FileSystemBlobStore", _FakeBlobStore)
    monkeypatch.setattr(composition_root, "LanceDBVectorIndex", _FakeVectorIndex)
    monkeypatch.setattr(
        composition_root,
        "build_sentence_transformer_embedder",
        _fake_build_embedder,
    )
    monkeypatch.setattr(composition_root, "build_docling_converter", _fake_build_converter)
    monkeypatch.setattr(composition_root, "build_openai_compat_client", _fake_build_llm_client)
    monkeypatch.setattr(composition_root, "build_s2_client", _fake_build_s2_client)

    container = composition_root.build_container(
        settings,
        llm_base_url="http://local",
        llm_api_key="token",
    )

    assert container.settings is settings
    assert container.handler_context.paper_store is container.paper_store
    assert container.handler_context.job_queue is container.job_queue
    assert container.handler_context.blob_store is container.blob_store
    assert container.handler_context.converter is container.converter
    assert container.handler_context.embedder is container.embedder
    assert container.handler_context.vector_index is container.vector_index
    assert container.handler_context.llm_client is container.llm_client
    assert container.handler_context.scholar_client is container.scholar_client
    assert container.handler_context.candidate_store is container.candidate_store
    assert container.job_runner.job_queue is container.job_queue
    assert container.job_runner.context is container.handler_context
    assert isinstance(container.blob_store, _FakeBlobStore)
    assert isinstance(container.vector_index, _FakeVectorIndex)
    assert isinstance(container.scholar_client, _FakeScholarClient)

    row = container.db.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'papers'"
    )
    assert row is not None


def test_load_settings_validation_failure(tmp_path: Path) -> None:
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
        # lancedb_dir missing on purpose

        [embeddings]
        model = "fake"
        dimension = 1
        text_slice_strategy = "markdown_full"

        [llm]
        default_profile = "default"

        [scholar]
        api_key = ""
        rate_limit_per_second = 10
        """,
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_settings(defaults_path=defaults_path)
