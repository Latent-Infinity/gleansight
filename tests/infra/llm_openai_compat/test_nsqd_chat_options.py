from __future__ import annotations

from typing import Any

from papers.infra.llm_openai_compat.client import OpenAICompatClient


def test_openai_compat_complete_merges_chat_options_and_metadata() -> None:
    captured: dict[str, Any] = {}

    def _send(
        payload: dict[str, Any], profile: dict[str, Any], timeout_s: int | None
    ) -> dict[str, Any]:
        captured["payload"] = payload
        captured["profile"] = profile
        captured["timeout_s"] = timeout_s
        return {
            "choices": [{"message": {"content": '{"label":"novel"}'}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5},
            "model": "qwen3.6:35b-a3b-q4_K_M",
            "system_fingerprint": "ollama:seeded",
            "created": 1_756_485_600,
        }

    response = OpenAICompatClient(send_func=_send).complete(
        prompt="prompt body",
        profile={
            "base_url": "http://127.0.0.1:11434",
            "chat_options": {
                "temperature": 0,
                "seed": 17,
                "response_format": {"type": "json_schema", "json_schema": {"name": "tau"}},
            },
        },
        model="qwen3.6:35b-a3b-q4_K_M",
        timeout_s=45,
    )

    assert captured["payload"]["temperature"] == 0
    assert captured["payload"]["seed"] == 17
    assert captured["payload"]["response_format"]["type"] == "json_schema"
    assert captured["payload"]["response_format"]["json_schema"] == {
        "name": "tau",
    }
    assert response.response_metadata == {
        "model": "qwen3.6:35b-a3b-q4_K_M",
        "system_fingerprint": "ollama:seeded",
        "created": 1_756_485_600,
    }
