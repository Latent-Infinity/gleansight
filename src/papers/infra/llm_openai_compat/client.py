from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from papers.app import ports
from papers.domain.errors import ErrorCode, PipelineError


@dataclass(frozen=True)
class OpenAICompatClient(ports.LLMClient):
    send_func: Callable[..., dict[str, Any]]

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
            "think": False,
        }
        chat_options = profile.get("chat_options")
        if isinstance(chat_options, dict):
            for key, value in chat_options.items():
                if isinstance(key, str):
                    payload[key] = value
        try:
            response = self.send_func(payload, profile, timeout_s)
        except TypeError:
            # Backward-compatible for tests and simple fakes that only accept payload.
            try:
                response = self.send_func(payload)
            except PipelineError:
                raise
            except Exception as exc:
                raise PipelineError(ErrorCode.LLM_ERROR, str(exc)) from exc
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(ErrorCode.LLM_ERROR, str(exc)) from exc
        text = _extract_text(response)
        return ports.LLMResponse(
            text=text,
            tokens_in=response.get("usage", {}).get("prompt_tokens"),
            tokens_out=response.get("usage", {}).get("completion_tokens"),
            cost_usd=response.get("cost"),
            response_metadata=_response_metadata(response),
        )


def build_openai_compat_client(*, base_url: str, api_key: str | None = None) -> OpenAICompatClient:
    try:
        import httpx
    except Exception as exc:  # pragma: no cover - optional dependency
        raise PipelineError(ErrorCode.NETWORK_ERROR, "httpx not installed") from exc

    def _send(
        payload: dict[str, Any],
        profile: dict[str, Any],
        timeout_s: int | None,
    ) -> dict[str, Any]:
        effective_base_url = str(profile.get("base_url") or base_url).rstrip("/")
        if "api_key" in profile:
            profile_api_key = profile.get("api_key")
            if profile_api_key is None:
                effective_api_key = None
            else:
                effective_api_key = str(profile_api_key)
        else:
            effective_api_key = api_key
        headers = {"Content-Type": "application/json"}
        if effective_api_key:
            headers["Authorization"] = f"Bearer {effective_api_key}"
        timeout = float(timeout_s) if timeout_s is not None else 30.0
        timeout_exc = getattr(httpx, "TimeoutException", TimeoutError)
        http_error_exc = getattr(httpx, "HTTPError", Exception)
        http_status_exc = getattr(httpx, "HTTPStatusError", http_error_exc)
        request_error_exc = getattr(httpx, "RequestError", http_error_exc)
        try:
            with httpx.Client(timeout=timeout) as client:
                url = f"{effective_base_url}/v1/chat/completions"
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except timeout_exc as exc:
            raise PipelineError(ErrorCode.LLM_TIMEOUT, str(exc)) from exc
        except http_status_exc as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 429:
                raise PipelineError(ErrorCode.RATE_LIMITED, str(exc)) from exc
            if isinstance(status_code, int) and 500 <= status_code < 600:
                raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc
            raise PipelineError(ErrorCode.LLM_ERROR, str(exc)) from exc
        except request_error_exc as exc:
            raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc
        except http_error_exc as exc:
            raise PipelineError(ErrorCode.LLM_ERROR, str(exc)) from exc

    return OpenAICompatClient(send_func=_send)


def _extract_text(response: dict[str, Any]) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except Exception as exc:
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid LLM response") from exc


def _response_metadata(response: dict[str, Any]) -> dict[str, Any] | None:
    metadata: dict[str, Any] = {}
    for key in ("model", "system_fingerprint", "service_tier", "created"):
        value = response.get(key)
        if value is not None:
            metadata[key] = value
    return metadata or None
