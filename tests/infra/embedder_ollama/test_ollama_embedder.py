from __future__ import annotations

import math

import pytest

from papers.config.settings import EmbeddingSettings
from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.embedder_ollama.adapter import (
    OpenAICompatEmbedder,
    build_configured_ollama_embedder,
    build_openai_compat_embedder,
)


def test_embedder_l2_normalizes_and_checks_dimension() -> None:
    captured: dict[str, object] = {}

    def _send(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {"data": [{"embedding": [3.0, 4.0]}]}

    embedder = OpenAICompatEmbedder(
        model_name_value="qwen3-embedding:latest",
        dimension_value=2,
        send_func=_send,
    )
    vector = embedder.embed("gamma imbalance")
    assert embedder.model_name() == "qwen3-embedding:latest"
    assert embedder.dimension() == 2
    assert captured["payload"] == {
        "model": "qwen3-embedding:latest",
        "input": "gamma imbalance",
    }
    assert vector == pytest.approx([0.6, 0.8])
    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)


def test_embedder_rejects_dimension_mismatch() -> None:
    embedder = OpenAICompatEmbedder(
        model_name_value="qwen3-embedding:latest",
        dimension_value=3,
        send_func=lambda _payload: {"data": [{"embedding": [1.0, 0.0]}]},
    )
    with pytest.raises(PipelineError) as excinfo:
        embedder.embed("text")
    assert excinfo.value.code is ErrorCode.EMBEDDING_FAILED


def test_build_embedder_posts_openai_compat_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types
    from typing import Any, cast

    fake_httpx = types.ModuleType("httpx")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"embedding": [0.0, 1.0]}]}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = TimeoutError
    fake_httpx_any.HTTPError = Exception
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    embedder = build_openai_compat_embedder(
        model_name="qwen3-embedding:latest",
        dimension=2,
        base_url="http://127.0.0.1:11434",
    )
    vector = embedder.embed("text")
    assert captured["url"] == "http://127.0.0.1:11434/v1/embeddings"
    assert captured["json"] == {"model": "qwen3-embedding:latest", "input": "text"}
    assert captured["headers"] == {"Content-Type": "application/json"}
    assert captured["timeout"] == 300.0
    assert vector == pytest.approx([0.0, 1.0])


def test_build_configured_ollama_embedder_omits_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types
    from typing import Any, cast

    fake_httpx = types.ModuleType("httpx")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"embedding": [0.0, 1.0]}]}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = TimeoutError
    fake_httpx_any.HTTPError = Exception
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    embedder = build_configured_ollama_embedder(
        EmbeddingSettings(
            model="qwen3-embedding:latest",
            dimension=2,
            text_slice_strategy="markdown_full",
            base_url="http://127.0.0.1:11434",
        )
    )

    vector = embedder.embed("text")

    assert captured["url"] == "http://127.0.0.1:11434/v1/embeddings"
    assert captured["json"] == {"model": "qwen3-embedding:latest", "input": "text"}
    assert captured["headers"] == {"Content-Type": "application/json"}
    assert captured["timeout"] == 300.0
    assert vector == pytest.approx([0.0, 1.0])


def test_build_embedder_with_api_key_sets_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types
    from typing import Any, cast

    fake_httpx = types.ModuleType("httpx")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"embedding": [0.0, 1.0]}]}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = TimeoutError
    fake_httpx_any.HTTPError = Exception
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    embedder = build_openai_compat_embedder(
        model_name="qwen3-embedding:latest",
        dimension=2,
        base_url="http://127.0.0.1:11434",
        api_key="secret-key",
    )

    vector = embedder.embed("text")

    assert captured["url"] == "http://127.0.0.1:11434/v1/embeddings"
    assert captured["json"] == {"model": "qwen3-embedding:latest", "input": "text"}
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret-key",
    }
    assert captured["timeout"] == 300.0
    assert vector == pytest.approx([0.0, 1.0])


def test_build_embedder_without_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original_import = builtins.__import__

    def _import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name.startswith("httpx"):
            raise ImportError("blocked")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)
    with pytest.raises(PipelineError) as excinfo:
        build_openai_compat_embedder(
            model_name="qwen3-embedding:latest",
            dimension=4096,
            base_url="http://127.0.0.1:11434",
        )
    assert excinfo.value.code is ErrorCode.NETWORK_ERROR
