from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from papers.app import ports
from papers.domain.errors import ErrorCode, PipelineError


@dataclass(frozen=True)
class OpenAICompatClient(ports.LLMClient):
    send_func: Callable[[dict[str, Any]], dict[str, Any]]

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> ports.LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response = self.send_func(payload)
        except Exception as exc:
            raise PipelineError(ErrorCode.LLM_ERROR, str(exc)) from exc
        text = _extract_text(response)
        return ports.LLMResponse(
            text=text,
            tokens_in=response.get("usage", {}).get("prompt_tokens"),
            tokens_out=response.get("usage", {}).get("completion_tokens"),
            cost_usd=response.get("cost"),
        )


def build_openai_compat_client(*, base_url: str, api_key: str | None = None) -> OpenAICompatClient:
    try:
        import httpx  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise PipelineError(ErrorCode.NETWORK_ERROR, "httpx not installed") from exc

    def _send(payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        with httpx.Client(timeout=30.0) as client:
            url = f"{base_url.rstrip('/')}/v1/chat/completions"
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    return OpenAICompatClient(send_func=_send)


def _extract_text(response: dict[str, Any]) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except Exception as exc:
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid LLM response") from exc
