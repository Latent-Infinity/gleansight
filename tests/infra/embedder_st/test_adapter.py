from __future__ import annotations

import sys
import types

import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.embedder_st.adapter import (
    SentenceTransformerEmbedder,
    build_sentence_transformer_embedder,
)


def test_build_embedder_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.ModuleType("sentence_transformers")
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    with pytest.raises(PipelineError) as excinfo:
        build_sentence_transformer_embedder("model")

    assert excinfo.value.code is ErrorCode.EMBEDDING_FAILED


def test_embedder_propagates_embed_errors() -> None:
    def _embed(_: str) -> list[float]:
        raise RuntimeError("boom")

    embedder = SentenceTransformerEmbedder(
        model_name_value="model",
        dimension_value=3,
        embed_func=_embed,
    )

    with pytest.raises(RuntimeError):
        embedder.embed("text")


def test_build_embedder_missing_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = types.ModuleType("sentence_transformers")

    class FakeModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def get_sentence_embedding_dimension(self) -> None:
            return None

    fake_st.SentenceTransformer = FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)

    with pytest.raises(PipelineError) as excinfo:
        build_sentence_transformer_embedder("model")

    assert excinfo.value.code is ErrorCode.EMBEDDING_FAILED
    assert "dimension" in str(excinfo.value).lower()


def test_build_embedder_success_with_fake() -> None:
    """Test successful build with fake SentenceTransformer."""
    from typing import Any, cast

    fake_st = types.ModuleType("sentence_transformers")

    class FakeModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def get_sentence_embedding_dimension(self) -> int:
            return 384

        def encode(self, text: str, normalize_embeddings: bool = False) -> Any:
            # Return a fake numpy-like object with tolist()
            class FakeArray:
                def tolist(self) -> list[float]:
                    return [1.0, 2.0, 3.0]

            return FakeArray()

    fake_st_any = cast(Any, fake_st)
    fake_st_any.SentenceTransformer = FakeModel

    import sys

    sys.modules["sentence_transformers"] = fake_st

    try:
        embedder = build_sentence_transformer_embedder("test-model")
        assert embedder.model_name() == "test-model"
        assert embedder.dimension() == 384
        result = embedder.embed("hello")
        assert result == [1.0, 2.0, 3.0]
    finally:
        # Clean up
        if "sentence_transformers" in sys.modules:
            del sys.modules["sentence_transformers"]
