from __future__ import annotations

import json
from typing import Any
from unittest.mock import Mock

import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.scholar_s2.adapter import SemanticScholarClient, build_s2_client


class TestSemanticScholarClient:
    """Test Semantic Scholar API adapter."""

    def test_search_returns_candidate_records_with_required_fields(self) -> None:
        """Search should return candidate records with all required fields."""
        mock_response = {
            "total": 2,
            "offset": 0,
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Deep Learning for NLP",
                    "year": 2020,
                    "venue": "ACL",
                    "authors": [
                        {"name": "Alice Smith"},
                        {"name": "Bob Jones"},
                    ],
                    "abstract": "This paper presents...",
                    "externalIds": {
                        "ArXiv": "2001.12345",
                        "DOI": "10.1000/xyz",
                    },
                },
                {
                    "paperId": "def456",
                    "title": "Attention Mechanisms",
                    "year": 2019,
                    "venue": None,
                    "authors": [{"name": "Charlie Brown"}],
                    "abstract": None,
                    "externalIds": None,
                },
            ],
        }

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            assert url == "https://api.semanticscholar.org/graph/v1/paper/search"
            assert params["query"] == "deep learning"
            return mock_response

        client = SemanticScholarClient(send_func=send_func)
        results = client.search(
            query="deep learning",
            filters={},
            max_results=10,
            page_size=100,
        )

        assert len(results) == 2
        # First result
        assert results[0]["source_paper_id"] == "abc123"
        assert results[0]["title"] == "Deep Learning for NLP"
        assert results[0]["year"] == 2020
        assert results[0]["venue"] == "ACL"
        assert results[0]["authors"] == ["Alice Smith", "Bob Jones"]
        assert results[0]["abstract"] == "This paper presents..."
        assert results[0]["external_ids"] == {
            "ArXiv": "2001.12345",
            "DOI": "10.1000/xyz",
        }
        # Second result
        assert results[1]["source_paper_id"] == "def456"
        assert results[1]["title"] == "Attention Mechanisms"
        assert results[1]["year"] == 2019
        assert results[1]["venue"] is None
        assert results[1]["authors"] == ["Charlie Brown"]
        assert results[1]["abstract"] is None
        assert results[1]["external_ids"] is None

    def test_search_handles_pagination_correctly(self) -> None:
        """Search should handle multiple pages correctly."""
        page1 = {
            "total": 250,
            "offset": 0,
            "data": [{"paperId": f"page1_{i}", "title": f"Paper {i}"} for i in range(100)],
        }
        page2 = {
            "total": 250,
            "offset": 100,
            "data": [{"paperId": f"page2_{i}", "title": f"Paper {i+100}"} for i in range(100)],
        }
        page3 = {
            "total": 250,
            "offset": 200,
            "data": [{"paperId": f"page3_{i}", "title": f"Paper {i+200}"} for i in range(50)],
        }

        call_count = 0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if params["offset"] == 0:
                return page1
            elif params["offset"] == 100:
                return page2
            elif params["offset"] == 200:
                return page3
            else:
                raise ValueError(f"Unexpected offset: {params['offset']}")

        client = SemanticScholarClient(send_func=send_func)
        results = client.search(
            query="test",
            filters={},
            max_results=250,
            page_size=100,
        )

        assert len(results) == 250
        assert call_count == 3
        assert results[0]["source_paper_id"] == "page1_0"
        assert results[100]["source_paper_id"] == "page2_0"
        assert results[200]["source_paper_id"] == "page3_0"

    def test_search_respects_max_results(self) -> None:
        """Search should stop when max_results is reached."""
        page1 = {
            "total": 1000,
            "offset": 0,
            "data": [{"paperId": f"p{i}", "title": f"Paper {i}"} for i in range(100)],
        }

        call_count = 0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return page1

        client = SemanticScholarClient(send_func=send_func)
        results = client.search(
            query="test",
            filters={},
            max_results=50,
            page_size=100,
        )

        assert len(results) == 50
        assert call_count == 1

    def test_search_handles_year_filter(self) -> None:
        """Search should pass year filter to API."""
        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            assert params["year"] == "2020-2025"
            return {"total": 0, "offset": 0, "data": []}

        client = SemanticScholarClient(send_func=send_func)
        client.search(
            query="test",
            filters={"year_min": 2020, "year_max": 2025},
            max_results=10,
            page_size=100,
        )

    def test_search_rate_limiting_with_retry(self) -> None:
        """Search should handle rate limit errors and retry."""
        call_count = 0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                exc = Exception("429 Too Many Requests")
                exc.status_code = 429  # type: ignore
                raise exc
            return {"total": 1, "offset": 0, "data": [{"paperId": "abc", "title": "Test"}]}

        client = SemanticScholarClient(send_func=send_func, retry_delay_s=0.01)
        results = client.search(query="test", filters={}, max_results=10, page_size=100)

        assert len(results) == 1
        assert call_count == 2

    def test_search_rate_limiting_exceeds_max_retries(self) -> None:
        """Search should fail after max retries on rate limit."""
        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            exc = Exception("429 Too Many Requests")
            exc.status_code = 429  # type: ignore
            raise exc

        client = SemanticScholarClient(send_func=send_func, max_retries=2, retry_delay_s=0.01)
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.RATE_LIMITED
        assert "rate limit" in str(exc_info.value).lower()

    def test_search_network_error_translation(self) -> None:
        """Network errors should be translated to domain errors."""
        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            raise ConnectionError("Network unreachable")

        client = SemanticScholarClient(send_func=send_func)
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.NETWORK_ERROR

    def test_search_timeout_error_translation(self) -> None:
        """Timeout errors should be translated to domain errors."""
        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            raise TimeoutError("Request timed out")

        client = SemanticScholarClient(send_func=send_func)
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.TIMEOUT

    def test_search_http_error_translation(self) -> None:
        """HTTP errors should be translated to domain errors."""
        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            exc = Exception("500 Internal Server Error")
            exc.status_code = 500  # type: ignore
            raise exc

        client = SemanticScholarClient(send_func=send_func)
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.NETWORK_ERROR

    def test_search_invalid_response_format(self) -> None:
        """Invalid response format should raise error."""
        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            return {"invalid": "response"}

        client = SemanticScholarClient(send_func=send_func)
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.OUTPUT_PARSE_FAILED


class TestBuildS2Client:
    """Test build_s2_client factory function."""

    def test_build_client_with_api_key(self) -> None:
        """Should build client with API key in headers."""
        client = build_s2_client(api_key="test_key")
        assert isinstance(client, SemanticScholarClient)

    def test_build_client_without_api_key(self) -> None:
        """Should build client without API key (works with S2 API)."""
        client = build_s2_client(api_key=None)
        assert isinstance(client, SemanticScholarClient)
