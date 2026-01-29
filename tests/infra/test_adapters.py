from __future__ import annotations

from pathlib import Path

import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.converter_docling.adapter import DoclingConverter
from papers.infra.embedder_st.adapter import SentenceTransformerEmbedder
from papers.infra.llm_openai_compat.client import OpenAICompatClient


def test_docling_converter_handles_exception(tmp_path: Path) -> None:
    def _fail(_: Path) -> str:
        raise RuntimeError("boom")

    converter = DoclingConverter(convert_func=_fail, version_str="1")
    result = converter.pdf_to_markdown(tmp_path / "missing.pdf")
    assert not result.ok
    assert result.error_code == ErrorCode.CONVERSION_FAILED


def test_docling_converter_empty_output(tmp_path: Path) -> None:
    """Test that empty or whitespace-only output is handled."""

    def _empty(_: Path) -> str:
        return "   \n  \t  "

    converter = DoclingConverter(convert_func=_empty, version_str="1.0")
    result = converter.pdf_to_markdown(tmp_path / "empty.pdf")
    assert not result.ok
    assert result.error_code == ErrorCode.EMPTY_OUTPUT
    assert result.error_message is not None
    assert "empty output" in result.error_message


def test_docling_converter_success(tmp_path: Path) -> None:
    """Test successful conversion."""

    def _convert(_: Path) -> str:
        return "# Title\n\nContent here"

    converter = DoclingConverter(convert_func=_convert, version_str="1.0")
    result = converter.pdf_to_markdown(tmp_path / "doc.pdf")
    assert result.ok
    assert result.markdown == "# Title\n\nContent here"
    assert result.error_code is None
    assert result.error_message is None


def test_docling_converter_version() -> None:
    """Test version method."""

    def _noop(_: Path) -> str:
        return "text"

    converter = DoclingConverter(convert_func=_noop, version_str="1.2.3")
    assert converter.version() == "1.2.3"


def test_embedder_uses_callable() -> None:
    embedder = SentenceTransformerEmbedder(
        model_name_value="model",
        dimension_value=3,
        embed_func=lambda text: [float(len(text))],
    )
    assert embedder.embed("abc") == [3.0]


def test_embedder_model_name() -> None:
    """Test model_name method."""
    embedder = SentenceTransformerEmbedder(
        model_name_value="test-model",
        dimension_value=128,
        embed_func=lambda text: [1.0] * 128,
    )
    assert embedder.model_name() == "test-model"


def test_embedder_dimension() -> None:
    """Test dimension method."""
    embedder = SentenceTransformerEmbedder(
        model_name_value="model",
        dimension_value=256,
        embed_func=lambda text: [0.0] * 256,
    )
    assert embedder.dimension() == 256


def test_openai_client_extracts_text() -> None:
    def _send(payload: dict) -> dict:
        return {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1}}

    client = OpenAICompatClient(send_func=_send)
    response = client.complete(prompt="hi", profile={}, model="m")
    assert response.text == "ok"
    assert response.tokens_in == 1


def test_openai_client_send_failure() -> None:
    def _send(payload: dict) -> dict:
        raise RuntimeError("boom")

    client = OpenAICompatClient(send_func=_send)
    with pytest.raises(PipelineError):
        client.complete(prompt="hi", profile={}, model="m")


def test_openai_client_invalid_response() -> None:
    def _send(payload: dict) -> dict:
        return {"choices": []}

    client = OpenAICompatClient(send_func=_send)
    with pytest.raises(PipelineError):
        client.complete(prompt="hi", profile={}, model="m")
