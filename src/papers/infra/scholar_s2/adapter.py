from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from papers.domain.errors import ErrorCode, PipelineError


@dataclass(frozen=True)
class SemanticScholarClient:
    """Semantic Scholar API client implementing ScholarClient protocol."""

    send_func: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
    max_retries: int = 3
    retry_delay_s: float = 1.0

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
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
        offset = 0
        url = "https://api.semanticscholar.org/graph/v1/paper/search"

        # Build query parameters
        params: dict[str, Any] = {
            "query": query,
            "limit": min(page_size, 100),  # API max is 100
            "offset": offset,
            "fields": "paperId,title,year,venue,authors,abstract,externalIds",
        }

        # Add year filter if provided
        if "year_min" in filters and "year_max" in filters:
            params["year"] = f"{filters['year_min']}-{filters['year_max']}"
        elif "year_min" in filters:
            params["year"] = f"{filters['year_min']}-"
        elif "year_max" in filters:
            params["year"] = f"-{filters['year_max']}"

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
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return self.send_func(url, params, headers)
            except TimeoutError as exc:
                raise PipelineError(ErrorCode.TIMEOUT, str(exc)) from exc
            except ConnectionError as exc:
                raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc
            except Exception as exc:
                # Check if it's a rate limit error
                status_code = getattr(exc, "status_code", None)
                if status_code == 429:
                    last_error = exc
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay_s * (attempt + 1))
                        continue
                    else:
                        raise PipelineError(
                            ErrorCode.RATE_LIMITED,
                            f"rate limit exceeded after {self.max_retries} retries",
                        ) from exc
                else:
                    raise PipelineError(ErrorCode.NETWORK_ERROR, str(exc)) from exc

        # Should not reach here, but satisfy type checker
        if last_error:
            raise PipelineError(
                ErrorCode.RATE_LIMITED,
                f"rate limit exceeded after {self.max_retries} retries",
            ) from last_error
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
            external_ids = item["externalIds"]

        return {
            "source_paper_id": item.get("paperId", ""),
            "title": item.get("title", ""),
            "year": item.get("year"),
            "venue": item.get("venue"),
            "authors": authors,
            "abstract": item.get("abstract"),
            "external_ids": external_ids,
        }


def build_s2_client(*, api_key: str | None = None) -> SemanticScholarClient:
    """Build Semantic Scholar client with httpx backend.

    Args:
        api_key: Optional S2 API key (increases rate limits)

    Returns:
        SemanticScholarClient instance
    """
    try:
        import httpx  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise PipelineError(ErrorCode.NETWORK_ERROR, "httpx not installed") from exc

    def _send(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if api_key:
            headers["x-api-key"] = api_key

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    return SemanticScholarClient(send_func=_send)
