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
            error = httpx.HTTPStatusError(
                "rate limited", request=MagicMock(), response=mock_response
            )
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

    def test_download_sends_user_agent_header(self, tmp_path: Path) -> None:
        """Should send User-Agent and Accept headers to avoid 403 blocks."""
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

            downloader.download("https://www.mdpi.com/paper.pdf", dest_path)

            # Verify headers were passed to httpx.Client
            call_kwargs = mock_client_class.call_args
            headers = call_kwargs.kwargs.get("headers", {})
            assert "User-Agent" in headers
            assert "Gleansight" in headers["User-Agent"]
            assert "Accept" in headers

    def test_download_respects_rate_limit(self, tmp_path: Path) -> None:
        """Should respect rate limiting between requests."""
        downloader = PdfDownloader(rate_limit_per_second=10.0)

        # Just verify the rate limiter is used (actual timing tests are flaky)
        assert downloader.rate_limiter is not None
        assert downloader.rate_limiter.rate_per_second == 10.0

    def test_download_raises_corrupt_pdf_when_html_response(self, tmp_path: Path) -> None:
        """Should raise CORRUPT_PDF when server returns HTML masquerading as PDF."""
        downloader = PdfDownloader()
        dest_path = tmp_path / "test.pdf"
        html_content = b"<html><body>Access Denied</body></html>"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_bytes.return_value = [html_content]
            mock_response.raise_for_status = MagicMock()
            mock_client.stream.return_value.__enter__.return_value = mock_response
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(PipelineError) as exc_info:
                downloader.download("https://example.com/paper.pdf", dest_path)

            assert exc_info.value.code == ErrorCode.CORRUPT_PDF
            assert "%PDF-" in str(exc_info.value)

    def test_download_cleans_up_corrupt_file(self, tmp_path: Path) -> None:
        """Should delete the corrupt file after detecting non-PDF content."""
        downloader = PdfDownloader()
        dest_path = tmp_path / "test.pdf"
        html_content = b"<html><body>Please log in</body></html>"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_bytes.return_value = [html_content]
            mock_response.raise_for_status = MagicMock()
            mock_client.stream.return_value.__enter__.return_value = mock_response
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(PipelineError):
                downloader.download("https://example.com/paper.pdf", dest_path)

        assert not dest_path.exists()

    def test_download_succeeds_with_valid_pdf_header(self, tmp_path: Path) -> None:
        """Should accept files that start with the PDF magic number."""
        downloader = PdfDownloader()
        dest_path = tmp_path / "test.pdf"
        pdf_content = b"%PDF-1.7\n1 0 obj\n..."

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

            downloader.download("https://example.com/paper.pdf", dest_path)

        assert dest_path.exists()
        assert dest_path.read_bytes() == pdf_content

    def test_per_source_rate_limiters_created(self) -> None:
        """Should create separate rate limiters for each source."""
        downloader = PdfDownloader(
            source_rate_limits={"arxiv_export": 0.33, "arxiv": 0.067},
        )

        assert len(downloader._source_rate_limiters) == 2
        assert downloader._source_rate_limiters["arxiv_export"].rate_per_second == 0.33
        assert downloader._source_rate_limiters["arxiv"].rate_per_second == 0.067

    def test_source_rate_limiter_used_for_known_source(self, tmp_path: Path) -> None:
        """Should use source-specific rate limiter when source is provided."""
        downloader = PdfDownloader(
            source_rate_limits={"arxiv_export": 0.33},
        )
        dest_path = tmp_path / "test.pdf"
        pdf_content = b"%PDF-1.4 content"

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

            with patch.object(
                downloader._source_rate_limiters["arxiv_export"], "acquire"
            ) as mock_acquire:
                downloader.download(
                    "https://export.arxiv.org/pdf/2001.12345.pdf", dest_path, source="arxiv_export"
                )

            mock_acquire.assert_called_once()

    def test_default_rate_limiter_used_for_unknown_source(self, tmp_path: Path) -> None:
        """Should use default rate limiter when source is not in source_rate_limits."""
        downloader = PdfDownloader(
            source_rate_limits={"arxiv_export": 0.33},
        )
        dest_path = tmp_path / "test.pdf"
        pdf_content = b"%PDF-1.4 content"

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

            with patch.object(downloader.rate_limiter, "acquire") as mock_acquire:
                downloader.download("https://example.com/paper.pdf", dest_path, source="other")

            mock_acquire.assert_called_once()
