from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from papers.domain.errors import ErrorCode, PipelineError


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate_per_second: float) -> None:
        self.rate_per_second = rate_per_second
        self.min_interval = 1.0 / rate_per_second
        self.last_request_time: float | None = None

    def acquire(self) -> None:
        """Wait if necessary to respect rate limit."""
        if self.last_request_time is None:
            self.last_request_time = time.time()
            return

        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        self.last_request_time = time.time()


@dataclass
class SemanticScholarClient:
    """Semantic Scholar API client implementing ScholarClient protocol."""

    send_func: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
    rate_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(10.0))
    max_retries: int = 3
    retry_delay_s: float = 1.0

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search for papers via Semantic Scholar API.

        Args:
            query: Search query string
            filters: Optional filters (year_min, year_max, etc.)
            max_results: Maximum number of results to return
            page_size: Results per page (API limit is 100)

        Returns:
            List of candidate dictionaries with required fields

        Raises:
            PipelineError: On network errors, rate limiting, or invalid responses
        """
        results: list[dict[str, Any]] = []
        offset = max(0, offset)
        url = "https://api.semanticscholar.org/graph/v1/paper/search"

        # Build query parameters
        params: dict[str, Any] = {
            "query": query,
            "limit": min(page_size, 100),  # API max is 100
            "offset": offset,
            "fields": "paperId,title,year,venue,authors,abstract,externalIds,openAccessPdf",
        }

        def _as_csv(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, (list, tuple, set)):
                items = [str(item).strip() for item in value if str(item).strip()]
                return ",".join(items) if items else None
            text = str(value).strip()
            return text or None

        # Add year filter if provided
        if "year_min" in filters and "year_max" in filters:
            params["year"] = f"{filters['year_min']}-{filters['year_max']}"
        elif "year_min" in filters:
            params["year"] = f"{filters['year_min']}-"
        elif "year_max" in filters:
            params["year"] = f"-{filters['year_max']}"

        publication_types = filters.get("publication_types") or filters.get("publicationTypes")
        if (value := _as_csv(publication_types)) is not None:
            params["publicationTypes"] = value

        fields_of_study = filters.get("fields_of_study") or filters.get("fieldsOfStudy")
        if (value := _as_csv(fields_of_study)) is not None:
            params["fieldsOfStudy"] = value

        venue = filters.get("venue")
        if (value := _as_csv(venue)) is not None:
            params["venue"] = value

        if "min_citation_count" in filters:
            try:
                params["minCitationCount"] = int(filters["min_citation_count"])
            except (TypeError, ValueError):
                pass

        if "open_access_pdf" in filters:
            params["openAccessPdf"] = bool(filters["open_access_pdf"])

        publication_date = filters.get("publication_date_or_year")
        if (value := _as_csv(publication_date)) is not None:
            params["publicationDateOrYear"] = value

        headers = {"Accept": "application/json"}

        while len(results) < max_results:
            params["offset"] = offset

            # Make request with retry logic
            response = self._send_with_retry(url, params, headers)

            # Parse response
            try:
                if "data" not in response:
                    raise PipelineError(
                        ErrorCode.OUTPUT_PARSE_FAILED,
                        "invalid API response format: missing 'data' field",
                    )
                data = response["data"]
            except (KeyError, AttributeError) as exc:
                raise PipelineError(
                    ErrorCode.OUTPUT_PARSE_FAILED,
                    "invalid API response format",
                ) from exc

            if not data:
                break

            # Transform results to candidate format
            for item in data:
                if len(results) >= max_results:
                    break

                candidate = self._transform_to_candidate(item)
                results.append(candidate)

            # Check if we have more pages
            total = response.get("total", 0)
            offset += len(data)
            if offset >= total:
                break

        return results

    def _send_with_retry(
        self,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Send request with retry logic for rate limiting."""
        last_error: Exception | None = None
        last_error_code: ErrorCode | None = None

        def _sleep_backoff(attempt: int) -> None:
            base_delay = self.retry_delay_s * (2**attempt)
            if base_delay > 30.0:
                base_delay = 30.0
            jitter = random.uniform(0.5, 1.5)
            time.sleep(base_delay * jitter)

        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.acquire()
                return self.send_func(url, params, headers)
            except TimeoutError as exc:
                last_error = exc
                last_error_code = ErrorCode.TIMEOUT
                if attempt < self.max_retries - 1:
                    _sleep_backoff(attempt)
                    continue
                raise PipelineError(ErrorCode.TIMEOUT, str(exc)) from exc
            except ConnectionError as exc:
                last_error = exc
                last_error_code = ErrorCode.NETWORK_ERROR
                if attempt < self.max_retries - 1:
                    _sleep_backoff(attempt)
                    continue
                raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc
            except Exception as exc:
                # Check if it's a rate limit error
                status_code = getattr(exc, "status_code", None)
                if status_code is None:
                    response = getattr(exc, "response", None)
                    status_code = getattr(response, "status_code", None)
                retryable_statuses = {429, 500, 502, 503, 504}
                if status_code in retryable_statuses:
                    last_error = exc
                    last_error_code = (
                        ErrorCode.RATE_LIMITED if status_code == 429 else ErrorCode.NETWORK_ERROR
                    )
                    if attempt < self.max_retries - 1:
                        _sleep_backoff(attempt)
                        continue
                    if status_code == 429:
                        raise PipelineError(
                            ErrorCode.RATE_LIMITED,
                            f"rate limit exceeded after {self.max_retries} retries",
                        ) from exc
                    raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc
                raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc

        # Should not reach here, but satisfy type checker
        if last_error and last_error_code:
            message = (
                f"rate limit exceeded after {self.max_retries} retries"
                if last_error_code == ErrorCode.RATE_LIMITED
                else str(last_error)
            )
            raise PipelineError(last_error_code, message) from last_error
        raise PipelineError(ErrorCode.NETWORK_ERROR, "unknown error")

    def _transform_to_candidate(self, item: dict[str, Any]) -> dict[str, Any]:
        """Transform S2 API result to candidate format."""
        # Extract author names
        authors = []
        if item.get("authors"):
            authors = [author.get("name", "") for author in item["authors"] if author.get("name")]

        # Extract external IDs
        external_ids = None
        if item.get("externalIds"):
            external_ids = dict(item["externalIds"])

        # Store open access PDF URL in external_ids for the resolver chain
        oa_pdf = item.get("openAccessPdf")
        if oa_pdf and oa_pdf.get("url"):
            if external_ids is None:
                external_ids = {}
            external_ids["OpenAccessPdf"] = oa_pdf["url"]

        return {
            "source_paper_id": item.get("paperId", ""),
            "title": item.get("title", ""),
            "year": item.get("year"),
            "venue": item.get("venue"),
            "authors": authors,
            "abstract": item.get("abstract"),
            "external_ids": external_ids,
        }


def build_s2_client(
    *,
    api_key: str | None = None,
    rate_limit_per_second: int = 10,
) -> SemanticScholarClient:
    """Build Semantic Scholar client with httpx backend.

    Args:
        api_key: Optional S2 API key (increases rate limits)
        rate_limit_per_second: Max requests per second (default: 10)

    Returns:
        SemanticScholarClient instance
    """
    try:
        import httpx
    except Exception as exc:  # pragma: no cover
        raise PipelineError(ErrorCode.NETWORK_ERROR, "httpx not installed") from exc

    def _send(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if api_key:
            headers["x-api-key"] = api_key

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    return SemanticScholarClient(
        send_func=_send,
        rate_limiter=RateLimiter(float(rate_limit_per_second)),
    )
