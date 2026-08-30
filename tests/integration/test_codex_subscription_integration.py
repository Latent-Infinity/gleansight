from __future__ import annotations

import os

import pytest

from papers.infra.llm_codex_subscription.client import CodexSubscriptionClient


@pytest.mark.integration
def test_codex_subscription_smoke() -> None:
    if os.environ.get("RUN_CODEX_INTEGRATION") != "1":
        pytest.skip("set RUN_CODEX_INTEGRATION=1 to run Codex subscription smoke")
    model = os.environ.get("CODEX_MODEL", "").strip()
    if not model:
        pytest.skip("set CODEX_MODEL to a ChatGPT-supported Codex model to run the smoke")
    response = CodexSubscriptionClient().complete(
        prompt=(
            "Return exactly this JSON object and nothing else: "
            '{"pair_id":"codex-smoke","label":"novel","rationale":"smoke"}'
        ),
        profile={
            "provider": "codex_subscription",
            "executable_path": "codex",
            "reasoning_effort": "high",
            "chat_options": {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "tau_label",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "pair_id": {"type": "string"},
                                "label": {
                                    "type": "string",
                                    "enum": ["near_duplicate", "novel", "ambiguous"],
                                },
                                "rationale": {"type": "string"},
                            },
                            "required": ["pair_id", "label", "rationale"],
                            "additionalProperties": False,
                        },
                    },
                }
            },
        },
        model=model,
        timeout_s=60,
    )
    assert response.text == '{"pair_id":"codex-smoke","label":"novel","rationale":"smoke"}'
    assert response.response_metadata is not None
    assert response.response_metadata["provider"] == "codex_subscription"
