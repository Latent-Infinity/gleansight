from __future__ import annotations

import builtins

import pytest

from papers.domain.errors import PipelineError
from papers.infra.converter_docling.adapter import build_docling_converter
from papers.infra.embedder_ollama.adapter import build_openai_compat_embedder
from papers.infra.embedder_st.adapter import build_sentence_transformer_embedder
from papers.infra.llm_openai_compat.client import build_openai_compat_client


def _block_import(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    original_import = builtins.__import__

    def _import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name.startswith(prefix):
            raise ImportError(f"blocked import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)


def test_build_docling_converter_without_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_import(monkeypatch, "docling")
    with pytest.raises(PipelineError):
        build_docling_converter()


def test_build_embedder_without_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_import(monkeypatch, "sentence_transformers")
    with pytest.raises(PipelineError):
        build_sentence_transformer_embedder("model")


def test_build_openai_client_without_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_import(monkeypatch, "httpx")
    with pytest.raises(PipelineError):
        build_openai_compat_client(base_url="http://localhost")


def test_build_ollama_embedder_without_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_import(monkeypatch, "httpx")
    with pytest.raises(PipelineError):
        build_openai_compat_embedder(
            model_name="qwen3-embedding:latest",
            dimension=4096,
            base_url="http://127.0.0.1:11434",
        )
