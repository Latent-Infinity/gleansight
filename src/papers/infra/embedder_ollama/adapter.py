from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from papers.app import ports
from papers.config.settings import EmbeddingSettings
from papers.domain.errors import ErrorCode, PipelineError

DEFAULT_QWEN_EMBEDDING_MODEL = "qwen3-embedding:latest"
DEFAULT_QWEN_EMBEDDING_DIMENSION = 4096
DEFAULT_EMBEDDING_TIMEOUT_S = 300.0


@dataclass(frozen=True)
class OpenAICompatEmbedder(ports.Embedder):
    model_name_value: str
    dimension_value: int
    send_func: Callable[[dict[str, Any]], dict[str, Any]]

    def model_name(self) -> str:
        return self.model_name_value

    def dimension(self) -> int:
        return self.dimension_value

    def model_id(self) -> str:
        model_id, _sep, _version = self.model_name_value.partition(":")
        return model_id or self.model_name_value

    def model_version(self) -> str:
        _model_id, sep, version = self.model_name_value.partition(":")
        return version if sep else "unspecified"

    def normalization_policy(self) -> str:
        return "l2"

    def embed(self, text: str) -> list[float]:
        response = self.send_func({"model": self.model_name_value, "input": text})
        vector = _embedding_from_response(response)
        if len(vector) != self.dimension_value:
            raise PipelineError(
                ErrorCode.EMBEDDING_FAILED,
                "embedding dimension does not match settings",
            )
        return _l2_normalize(vector)


def build_openai_compat_embedder(
    *,
    model_name: str,
    dimension: int,
    base_url: str,
    api_key: str | None = None,
    timeout_s: float = DEFAULT_EMBEDDING_TIMEOUT_S,
) -> OpenAICompatEmbedder:
    try:
        import httpx
    except Exception as exc:  # pragma: no cover - optional dependency
        raise PipelineError(ErrorCode.NETWORK_ERROR, "httpx not installed") from exc

    def _send(payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        timeout_exc = getattr(httpx, "TimeoutException", TimeoutError)
        http_error_exc = getattr(httpx, "HTTPError", Exception)
        try:
            with httpx.Client(timeout=timeout_s) as client:
                url = f"{base_url.rstrip('/')}/v1/embeddings"
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
        except timeout_exc as nested:
            raise PipelineError(ErrorCode.TIMEOUT, str(nested)) from nested
        except http_error_exc as nested:
            raise PipelineError(ErrorCode.EMBEDDING_FAILED, str(nested)) from nested
        if not isinstance(body, dict):
            raise PipelineError(ErrorCode.EMBEDDING_FAILED, "invalid embedding response")
        return body

    return OpenAICompatEmbedder(
        model_name_value=model_name,
        dimension_value=dimension,
        send_func=_send,
    )


def build_configured_ollama_embedder(settings: EmbeddingSettings) -> OpenAICompatEmbedder:
    return build_openai_compat_embedder(
        model_name=settings.model,
        dimension=settings.dimension,
        base_url=settings.base_url,
        api_key=None,
    )


def _embedding_from_response(response: dict[str, Any]) -> list[float]:
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            raw = first.get("embedding")
            if isinstance(raw, list) and all(isinstance(value, (int, float)) for value in raw):
                return [float(value) for value in raw]
    raise PipelineError(ErrorCode.EMBEDDING_FAILED, "invalid embedding response")


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
