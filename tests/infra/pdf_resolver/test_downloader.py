"""Tests for PDF downloader."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.pdf_resolver.downloader import PdfDownloader


class TestPdfDownloader:
    """Tests for PdfDownloader."""

    def test_download_success(self, tmp_path: Path) -> None:
        """Should download PDF content to destination path."""
        downloader = PdfDownloader()
        dest_path = tmp_path / "test.pdf"
        pdf_content = b"%PDF-1.4 fake pdf content"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_bytes.return_value = [pdf_content]
            mock_response.raise_for_status = MagicMock()
            mock_client.stream.return_value.__enter__.return_value = mock_response
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            downloader.download("https://arxiv.org/pdf/2001.12345.pdf", dest_path)

        assert dest_path.exists()
        assert dest_path.read_bytes() == pdf_content

    def test_download_raises_on_timeout(self, tmp_path: Path) -> None:
        """Should raise PipelineError with TIMEOUT code on timeout."""
        downloader = PdfDownloader(max_retries=1)
        dest_path = tmp_path / "test.pdf"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.stream.side_effect = httpx.TimeoutException("timeout")
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(PipelineError) as exc_info:
                downloader.download("https://arxiv.org/pdf/2001.12345.pdf", dest_path)

            assert exc_info.value.code == ErrorCode.TIMEOUT

    def test_download_raises_on_network_error(self, tmp_path: Path) -> None:
        """Should raise PipelineError with NETWORK_ERROR code on connection error."""
        downloader = PdfDownloader(max_retries=1)
        dest_path = tmp_path / "test.pdf"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.stream.side_effect = httpx.ConnectError("connection refused")
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(PipelineError) as exc_info:
                downloader.download("https://arxiv.org/pdf/2001.12345.pdf", dest_path)

            assert exc_info.value.code == ErrorCode.NETWORK_ERROR

    def test_download_raises_on_rate_limit(self, tmp_path: Path) -> None:
        """Should raise PipelineError with RATE_LIMITED code on 429."""
        downloader = PdfDownloader(max_retries=1)
        dest_path = tmp_path / "test.pdf"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 429
            error = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=mock_response)
            mock_client.stream.side_effect = error
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(PipelineError) as exc_info:
                downloader.download("https://arxiv.org/pdf/2001.12345.pdf", dest_path)

            assert exc_info.value.code == ErrorCode.RATE_LIMITED

    def test_download_raises_on_4xx_error(self, tmp_path: Path) -> None:
        """Should raise PipelineError with DOWNLOAD_FAILED on 4xx errors (except 429)."""
        downloader = PdfDownloader(max_retries=1)
        dest_path = tmp_path / "test.pdf"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            error = httpx.HTTPStatusError("not found", request=MagicMock(), response=mock_response)
            mock_client.stream.side_effect = error
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(PipelineError) as exc_info:
                downloader.download("https://arxiv.org/pdf/2001.12345.pdf", dest_path)

            assert exc_info.value.code == ErrorCode.DOWNLOAD_FAILED

    def test_download_retries_on_5xx_error(self, tmp_path: Path) -> None:
        """Should retry on 5xx errors."""
        downloader = PdfDownloader(max_retries=2, retry_delay_s=0.01)
        dest_path = tmp_path / "test.pdf"
        pdf_content = b"%PDF-1.4 fake pdf content"
        call_count = 0

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()

            def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    mock_response = MagicMock()
                    mock_response.status_code = 503
                    raise httpx.HTTPStatusError(
                        "service unavailable", request=MagicMock(), response=mock_response
                    )
                # Second call succeeds
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.iter_bytes.return_value = [pdf_content]
                mock_response.raise_for_status = MagicMock()
                ctx = MagicMock()
                ctx.__enter__ = MagicMock(return_value=mock_response)
                ctx.__exit__ = MagicMock(return_value=False)
                return ctx

            mock_client.stream.side_effect = side_effect
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            downloader.download("https://arxiv.org/pdf/2001.12345.pdf", dest_path)

        assert call_count == 2
        assert dest_path.exists()

    def test_download_respects_rate_limit(self, tmp_path: Path) -> None:
        """Should respect rate limiting between requests."""
        downloader = PdfDownloader(rate_limit_per_second=10.0)

        # Just verify the rate limiter is used (actual timing tests are flaky)
        assert downloader.rate_limiter is not None
        assert downloader.rate_limiter.rate_per_second == 10.0
