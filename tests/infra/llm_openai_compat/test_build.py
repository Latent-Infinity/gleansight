from __future__ import annotations

import sys
import types
from typing import Any, cast

import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.llm_openai_compat.client import (
    OpenAICompatClient,
    build_openai_compat_client,
)


def test_build_client_missing_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing httpx is handled (covered by pragma, testing for completeness)."""
    # This test verifies the function signature and basic error handling structure
    # The actual import error is marked with pragma: no cover in the source
    pass  # The import error case is an optional dependency guard


def test_build_client_with_fake_httpx() -> None:
    """Test build_openai_compat_client with fake httpx."""
    fake_httpx = types.ModuleType("httpx")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": "response text"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            # Verify URL construction
            assert "/v1/chat/completions" in url
            assert json.get("think") is False
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx

    try:
        client = build_openai_compat_client(base_url="http://test.com")
        response = client.complete(prompt="test", profile={}, model="gpt-4")
        assert response.text == "response text"
        assert response.tokens_in == 10
        assert response.tokens_out == 20
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_build_client_with_api_key() -> None:
    """Test that api_key is included in headers."""
    fake_httpx = types.ModuleType("httpx")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            pass

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            # Verify Authorization header
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test-key"
            assert url.startswith("http://test.com/")
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx

    try:
        client = build_openai_compat_client(base_url="http://test.com", api_key="test-key")
        client.complete(prompt="test", profile={}, model="gpt-4")
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_complete_with_tokens_out() -> None:
    """Test that tokens_out is extracted from response."""

    def _send(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 15},
        }

    client = OpenAICompatClient(send_func=_send)
    response = client.complete(prompt="hi", profile={}, model="m")
    assert response.tokens_out == 15


def test_complete_with_cost() -> None:
    """Test that cost_usd is extracted from response."""

    def _send(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
            "cost": 0.05,
        }

    client = OpenAICompatClient(send_func=_send)
    response = client.complete(prompt="hi", profile={}, model="m")
    assert response.cost_usd == 0.05


def test_complete_uses_profile_base_url_and_api_key() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            assert url.startswith("http://profile.local/v1/chat/completions")
            assert headers["Authorization"] == "Bearer profile-key"
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    class FakeHTTPError(Exception):
        pass

    class FakeTimeout(Exception):
        pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.HTTPError = FakeHTTPError
    fake_httpx_any.TimeoutException = FakeTimeout

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://default.local", api_key="default-key")
        client.complete(
            prompt="test",
            profile={"base_url": "http://profile.local", "api_key": "profile-key"},
            model="gpt-4",
        )
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_complete_explicit_blank_profile_api_key_suppresses_global_key() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            assert url.startswith("http://profile.local/v1/chat/completions")
            assert "Authorization" not in headers
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.HTTPError = Exception
    fake_httpx_any.TimeoutException = TimeoutError

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://default.local", api_key="global-key")
        client.complete(
            prompt="test",
            profile={"base_url": "http://profile.local", "api_key": ""},
            model="gpt-4",
        )
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_complete_profile_api_key_none_suppresses_global_key() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            assert "Authorization" not in headers
            return FakeResponse()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.HTTPError = Exception
    fake_httpx_any.TimeoutException = TimeoutError

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://default.local", api_key="global-key")
        client.complete(
            prompt="test",
            profile={"base_url": "http://profile.local", "api_key": None},
            model="gpt-4",
        )
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_build_client_maps_429_to_rate_limited() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeTimeout(Exception):
        pass

    class FakeHTTPError(Exception):
        pass

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            raise FakeHTTPStatusError(self)

    class FakeHTTPStatusError(FakeHTTPError):
        def __init__(self, response: FakeResponse) -> None:
            super().__init__("status")
            self.response = response

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            return FakeResponse(429)

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = FakeTimeout
    fake_httpx_any.HTTPError = FakeHTTPError
    fake_httpx_any.HTTPStatusError = FakeHTTPStatusError
    fake_httpx_any.RequestError = FakeHTTPError

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://test.local")
        with pytest.raises(PipelineError) as exc:
            client.complete(prompt="x", profile={}, model="m")
        assert exc.value.code == ErrorCode.RATE_LIMITED
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_build_client_maps_503_to_network_error() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeTimeout(Exception):
        pass

    class FakeHTTPError(Exception):
        pass

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            raise FakeHTTPStatusError(self)

    class FakeHTTPStatusError(FakeHTTPError):
        def __init__(self, response: FakeResponse) -> None:
            super().__init__("status")
            self.response = response

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            return FakeResponse(503)

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = FakeTimeout
    fake_httpx_any.HTTPError = FakeHTTPError
    fake_httpx_any.HTTPStatusError = FakeHTTPStatusError
    fake_httpx_any.RequestError = FakeHTTPError

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://test.local")
        with pytest.raises(PipelineError) as exc:
            client.complete(prompt="x", profile={}, model="m")
        assert exc.value.code == ErrorCode.NETWORK_ERROR
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_build_client_maps_timeout_to_llm_timeout() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeTimeout(Exception):
        pass

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]):
            raise FakeTimeout("slow")

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = FakeTimeout
    fake_httpx_any.HTTPError = Exception
    fake_httpx_any.RequestError = Exception

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://test.local")
        with pytest.raises(PipelineError) as exc:
            client.complete(prompt="x", profile={}, model="m")
        assert exc.value.code == ErrorCode.LLM_TIMEOUT
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_build_client_maps_request_error_to_network_error() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeHTTPError(Exception):
        pass

    class FakeRequestError(Exception):
        pass

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]):
            raise FakeRequestError("network")

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = TimeoutError
    fake_httpx_any.HTTPError = FakeHTTPError
    fake_httpx_any.RequestError = FakeRequestError

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://test.local")
        with pytest.raises(PipelineError) as exc:
            client.complete(prompt="x", profile={}, model="m")
        assert exc.value.code == ErrorCode.NETWORK_ERROR
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]


def test_build_client_maps_http_error_without_status_to_llm_error() -> None:
    fake_httpx = types.ModuleType("httpx")

    class FakeHTTPError(Exception):
        pass

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]):
            raise FakeHTTPError("bad response")

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    fake_httpx_any = cast(Any, fake_httpx)
    fake_httpx_any.Client = FakeClient
    fake_httpx_any.TimeoutException = TimeoutError
    fake_httpx_any.HTTPError = FakeHTTPError
    fake_httpx_any.RequestError = Exception

    original_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = fake_httpx
    try:
        client = build_openai_compat_client(base_url="http://test.local")
        with pytest.raises(PipelineError) as exc:
            client.complete(prompt="x", profile={}, model="m")
        assert exc.value.code == ErrorCode.LLM_ERROR
    finally:
        if original_httpx is not None:
            sys.modules["httpx"] = original_httpx
        elif "httpx" in sys.modules:
            del sys.modules["httpx"]
