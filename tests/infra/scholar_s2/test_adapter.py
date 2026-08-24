from __future__ import annotations

from typing import Any

import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.scholar_s2.adapter import RateLimiter, SemanticScholarClient, build_s2_client


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_rate_limiter_enforces_minimum_interval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = _FakeClock()
        monkeypatch.setattr("papers.infra.scholar_s2.adapter.time.time", clock.time)
        monkeypatch.setattr("papers.infra.scholar_s2.adapter.time.sleep", clock.sleep)
        limiter = RateLimiter(rate_per_second=10.0)
        limiter.acquire()
        limiter.acquire()
        assert clock.now == pytest.approx(0.1)

    def test_rate_limiter_allows_high_rate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = _FakeClock()
        monkeypatch.setattr("papers.infra.scholar_s2.adapter.time.time", clock.time)
        monkeypatch.setattr("papers.infra.scholar_s2.adapter.time.sleep", clock.sleep)
        limiter = RateLimiter(rate_per_second=100.0)
        limiter.acquire()
        limiter.acquire()
        assert clock.now == pytest.approx(0.01)


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
            "data": [{"paperId": f"page2_{i}", "title": f"Paper {i + 100}"} for i in range(100)],
        }
        page3 = {
            "total": 250,
            "offset": 200,
            "data": [{"paperId": f"page3_{i}", "title": f"Paper {i + 200}"} for i in range(50)],
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

    def test_search_starts_from_requested_offset(self) -> None:
        observed_offsets: list[int] = []

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            observed_offsets.append(params["offset"])
            return {
                "total": 11,
                "offset": params["offset"],
                "data": [{"paperId": "p10", "title": "Paper 10"}],
            }

        client = SemanticScholarClient(send_func=send_func)
        results = client.search(
            query="test",
            filters={},
            max_results=1,
            page_size=1,
            offset=10,
        )

        assert observed_offsets == [10]
        assert [result["source_paper_id"] for result in results] == ["p10"]

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

    def test_search_network_error_translation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Network errors should be translated to domain errors."""

        class FakeRateLimiter:
            def acquire(self) -> None:
                return None

        sleeps: list[float] = []

        def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        def fake_jitter(_: float, __: float) -> float:
            return 1.0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            raise ConnectionError("Network unreachable")

        import papers.infra.scholar_s2.adapter as adapter

        monkeypatch.setattr(adapter.time, "sleep", fake_sleep)
        monkeypatch.setattr(adapter.random, "uniform", fake_jitter)

        client = SemanticScholarClient(
            send_func=send_func,
            rate_limiter=FakeRateLimiter(),
            max_retries=3,
            retry_delay_s=0.5,
        )
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.NETWORK_ERROR
        assert len(sleeps) == 2

    def test_search_timeout_error_translation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Timeout errors should be translated to domain errors."""

        class FakeRateLimiter:
            def acquire(self) -> None:
                return None

        sleeps: list[float] = []

        def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        def fake_jitter(_: float, __: float) -> float:
            return 1.0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            raise TimeoutError("Request timed out")

        import papers.infra.scholar_s2.adapter as adapter

        monkeypatch.setattr(adapter.time, "sleep", fake_sleep)
        monkeypatch.setattr(adapter.random, "uniform", fake_jitter)

        client = SemanticScholarClient(
            send_func=send_func,
            rate_limiter=FakeRateLimiter(),
            max_retries=3,
            retry_delay_s=0.5,
        )
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.TIMEOUT
        assert len(sleeps) == 2

    def test_search_http_error_translation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTTP errors should be translated to domain errors."""

        class FakeRateLimiter:
            def acquire(self) -> None:
                return None

        sleeps: list[float] = []

        def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        def fake_jitter(_: float, __: float) -> float:
            return 1.0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            exc = Exception("500 Internal Server Error")
            exc.status_code = 500  # type: ignore
            raise exc

        import papers.infra.scholar_s2.adapter as adapter

        monkeypatch.setattr(adapter.time, "sleep", fake_sleep)
        monkeypatch.setattr(adapter.random, "uniform", fake_jitter)

        client = SemanticScholarClient(
            send_func=send_func,
            rate_limiter=FakeRateLimiter(),
            max_retries=3,
            retry_delay_s=0.5,
        )
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.NETWORK_ERROR
        assert len(sleeps) == 2

    def test_retry_backoff_caps_at_30s(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Backoff should be exponential with jitter and capped at 30s."""

        class FakeRateLimiter:
            def acquire(self) -> None:
                return None

        sleeps: list[float] = []

        def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        def fake_jitter(_: float, __: float) -> float:
            return 1.0

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            exc = Exception("429 Too Many Requests")
            exc.status_code = 429  # type: ignore
            raise exc

        import papers.infra.scholar_s2.adapter as adapter

        monkeypatch.setattr(adapter.time, "sleep", fake_sleep)
        monkeypatch.setattr(adapter.random, "uniform", fake_jitter)

        client = SemanticScholarClient(
            send_func=send_func,
            rate_limiter=FakeRateLimiter(),
            max_retries=4,
            retry_delay_s=20.0,
        )
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.RATE_LIMITED
        assert sleeps == [20.0, 30.0, 30.0]

    def test_search_invalid_response_format(self) -> None:
        """Invalid response format should raise error."""

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            return {"invalid": "response"}

        client = SemanticScholarClient(send_func=send_func)
        with pytest.raises(PipelineError) as exc_info:
            client.search(query="test", filters={}, max_results=10, page_size=100)

        assert exc_info.value.code == ErrorCode.OUTPUT_PARSE_FAILED

    def test_search_respects_rate_limit(self) -> None:
        """Search should use rate limiter to enforce rate limits."""
        import time

        call_times: list[float] = []

        def send_func(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
            call_times.append(time.time())
            # Return minimal valid response
            return {"total": 2, "offset": 0, "data": [{"paperId": "p1"}, {"paperId": "p2"}]}

        # Create client with 10 req/s rate limit (0.1s minimum interval)
        client = SemanticScholarClient(
            send_func=send_func,
            rate_limiter=RateLimiter(rate_per_second=10.0),
        )

        client.search(query="test", filters={}, max_results=2, page_size=100)

        # Should have made 1 call
        assert len(call_times) == 1


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

    def test_build_client_with_custom_rate_limit(self) -> None:
        """Should build client with custom rate limit."""
        client = build_s2_client(api_key=None, rate_limit_per_second=100)
        assert isinstance(client, SemanticScholarClient)
        assert client.rate_limiter.rate_per_second == 100.0

    def test_build_client_default_rate_limit(self) -> None:
        """Should build client with default rate limit of 10 req/s."""
        client = build_s2_client(api_key=None)
        assert isinstance(client, SemanticScholarClient)
        assert client.rate_limiter.rate_per_second == 10.0


class TestTransformToCandidate:
    """Tests for _transform_to_candidate."""

    def _make_client(self) -> SemanticScholarClient:
        return SemanticScholarClient(send_func=lambda *a: {})

    def test_open_access_pdf_stored_in_external_ids(self) -> None:
        client = self._make_client()
        item = {
            "paperId": "abc",
            "title": "Test",
            "externalIds": {"DOI": "10.1234/abc"},
            "openAccessPdf": {"url": "https://example.com/paper.pdf", "status": "GREEN"},
        }

        result = client._transform_to_candidate(item)

        assert result["external_ids"]["OpenAccessPdf"] == "https://example.com/paper.pdf"
        assert result["external_ids"]["DOI"] == "10.1234/abc"

    def test_no_open_access_pdf_leaves_external_ids_unchanged(self) -> None:
        client = self._make_client()
        item = {
            "paperId": "abc",
            "title": "Test",
            "externalIds": {"DOI": "10.1234/abc"},
        }

        result = client._transform_to_candidate(item)

        assert "OpenAccessPdf" not in result["external_ids"]

    def test_open_access_pdf_without_url_ignored(self) -> None:
        client = self._make_client()
        item = {
            "paperId": "abc",
            "title": "Test",
            "externalIds": {"DOI": "10.1234/abc"},
            "openAccessPdf": {"status": "CLOSED"},
        }

        result = client._transform_to_candidate(item)

        assert "OpenAccessPdf" not in result["external_ids"]

    def test_open_access_pdf_creates_external_ids_when_none(self) -> None:
        client = self._make_client()
        item = {
            "paperId": "abc",
            "title": "Test",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }

        result = client._transform_to_candidate(item)

        assert result["external_ids"]["OpenAccessPdf"] == "https://example.com/paper.pdf"
