"""PDF downloader with retry and rate limiting."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.scholar_s2.adapter import RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class PdfDownloader:
    """Downloads PDFs with retry logic and rate limiting."""

    rate_limit_per_second: float = 2.0
    max_retries: int = 3
    retry_delay_s: float = 1.0
    timeout_s: float = 120.0
    rate_limiter: RateLimiter = field(init=False)

    def __post_init__(self) -> None:
        self.rate_limiter = RateLimiter(self.rate_limit_per_second)

    def download(self, url: str, dest_path: Path) -> None:
        """Download PDF from URL to destination path.

        Args:
            url: URL to download from
            dest_path: Path to save downloaded PDF

        Raises:
            PipelineError: On download failure with appropriate error code:
                - TIMEOUT: Request timed out
                - RATE_LIMITED: Got 429 response
                - NETWORK_ERROR: Connection error or 5xx response
                - DOWNLOAD_FAILED: 4xx response (except 429)
        """
        last_error: Exception | None = None
        last_error_code: ErrorCode | None = None

        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.acquire()
                self._do_download(url, dest_path)
                logger.info("Downloaded PDF from %s to %s", url, dest_path)
                return
            except httpx.TimeoutException as exc:
                last_error = exc
                last_error_code = ErrorCode.TIMEOUT
                logger.warning("Timeout downloading %s (attempt %d/%d)", url, attempt + 1, self.max_retries)
                if attempt < self.max_retries - 1:
                    self._sleep_backoff(attempt)
                    continue
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = exc
                last_error_code = ErrorCode.NETWORK_ERROR
                logger.warning("Network error downloading %s (attempt %d/%d): %s", url, attempt + 1, self.max_retries, exc)
                if attempt < self.max_retries - 1:
                    self._sleep_backoff(attempt)
                    continue
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    last_error = exc
                    last_error_code = ErrorCode.RATE_LIMITED
                    logger.warning("Rate limited downloading %s (attempt %d/%d)", url, attempt + 1, self.max_retries)
                    if attempt < self.max_retries - 1:
                        self._sleep_backoff(attempt, base_multiplier=2.0)
                        continue
                elif 500 <= status_code < 600:
                    last_error = exc
                    last_error_code = ErrorCode.NETWORK_ERROR
                    logger.warning("Server error %d downloading %s (attempt %d/%d)", status_code, url, attempt + 1, self.max_retries)
                    if attempt < self.max_retries - 1:
                        self._sleep_backoff(attempt)
                        continue
                else:
                    # 4xx errors (except 429) are permanent failures
                    logger.error("Download failed with status %d for %s", status_code, url)
                    raise PipelineError(
                        ErrorCode.DOWNLOAD_FAILED,
                        f"HTTP {status_code}: {exc}",
                    ) from exc

        # All retries exhausted
        if last_error and last_error_code:
            message = f"{last_error_code}: {last_error}"
            raise PipelineError(last_error_code, message) from last_error
        raise PipelineError(ErrorCode.NETWORK_ERROR, "unknown error")

    def _do_download(self, url: str, dest_path: Path) -> None:
        """Perform the actual download."""
        with httpx.Client(timeout=self.timeout_s, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with dest_path.open("wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)

    def _sleep_backoff(self, attempt: int, base_multiplier: float = 1.0) -> None:
        """Sleep with exponential backoff and jitter."""
        base_delay = self.retry_delay_s * (2 ** attempt) * base_multiplier
        if base_delay > 60.0:
            base_delay = 60.0
        jitter = random.uniform(0.5, 1.5)
        time.sleep(base_delay * jitter)
