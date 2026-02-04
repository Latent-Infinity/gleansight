"""Tests for PDF resolvers."""

from __future__ import annotations

import pytest

from papers.app.ports import ResolvedPdf
from papers.infra.pdf_resolver.resolver import (
    ArxivPdfResolver,
    ChainedPdfResolver,
    UnpaywallPdfResolver,
)


class TestArxivPdfResolver:
    """Tests for ArxivPdfResolver."""

    def test_resolve_with_arxiv_id(self) -> None:
        """Should return arxiv PDF URL when ArXiv ID is present."""
        resolver = ArxivPdfResolver()
        external_ids = {"ArXiv": "2001.12345"}

        result = resolver.resolve(external_ids)

        assert result is not None
        assert result.url == "https://arxiv.org/pdf/2001.12345.pdf"
        assert result.source == "arxiv"

    def test_resolve_with_arxiv_id_lowercase(self) -> None:
        """Should handle lowercase 'arxiv' key."""
        resolver = ArxivPdfResolver()
        external_ids = {"arxiv": "2001.12345"}

        result = resolver.resolve(external_ids)

        assert result is not None
        assert result.url == "https://arxiv.org/pdf/2001.12345.pdf"

    def test_resolve_returns_none_without_arxiv_id(self) -> None:
        """Should return None when no ArXiv ID is present."""
        resolver = ArxivPdfResolver()
        external_ids = {"DOI": "10.1234/abc"}

        result = resolver.resolve(external_ids)

        assert result is None

    def test_resolve_returns_none_with_empty_dict(self) -> None:
        """Should return None for empty external IDs."""
        resolver = ArxivPdfResolver()

        result = resolver.resolve({})

        assert result is None

    def test_resolve_with_version_suffix(self) -> None:
        """Should handle ArXiv IDs with version suffix."""
        resolver = ArxivPdfResolver()
        external_ids = {"ArXiv": "2001.12345v2"}

        result = resolver.resolve(external_ids)

        assert result is not None
        assert result.url == "https://arxiv.org/pdf/2001.12345v2.pdf"


class TestUnpaywallPdfResolver:
    """Tests for UnpaywallPdfResolver."""

    def test_resolve_returns_none_without_doi(self) -> None:
        """Should return None when no DOI is present."""
        resolver = UnpaywallPdfResolver(email="test@example.com")
        external_ids = {"ArXiv": "2001.12345"}

        result = resolver.resolve(external_ids)

        assert result is None

    def test_resolve_returns_none_with_empty_dict(self) -> None:
        """Should return None for empty external IDs."""
        resolver = UnpaywallPdfResolver(email="test@example.com")

        result = resolver.resolve({})

        assert result is None

    def test_resolve_returns_none_without_email(self) -> None:
        """Should return None when email is not configured."""
        resolver = UnpaywallPdfResolver(email=None)
        external_ids = {"DOI": "10.1234/abc"}

        result = resolver.resolve(external_ids)

        assert result is None


class TestChainedPdfResolver:
    """Tests for ChainedPdfResolver."""

    def test_resolve_tries_resolvers_in_order(self) -> None:
        """Should return result from first successful resolver."""
        arxiv_resolver = ArxivPdfResolver()
        unpaywall_resolver = UnpaywallPdfResolver(email="test@example.com")
        chained = ChainedPdfResolver([arxiv_resolver, unpaywall_resolver])

        # ArXiv ID present, should use ArXiv resolver first
        external_ids = {"ArXiv": "2001.12345", "DOI": "10.1234/abc"}
        result = chained.resolve(external_ids)

        assert result is not None
        assert result.source == "arxiv"

    def test_resolve_falls_back_to_next_resolver(self) -> None:
        """Should fall back to next resolver if first returns None."""

        class FakeResolver:
            def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
                return ResolvedPdf(url="https://fake.com/pdf", source="fake")

        chained = ChainedPdfResolver([ArxivPdfResolver(), FakeResolver()])

        # No ArXiv ID, should fall back to FakeResolver
        external_ids = {"DOI": "10.1234/abc"}
        result = chained.resolve(external_ids)

        assert result is not None
        assert result.source == "fake"

    def test_resolve_returns_none_when_all_fail(self) -> None:
        """Should return None when all resolvers fail."""
        chained = ChainedPdfResolver([ArxivPdfResolver()])

        # No ArXiv ID
        external_ids = {"DOI": "10.1234/abc"}
        result = chained.resolve(external_ids)

        assert result is None

    def test_resolve_with_empty_resolvers(self) -> None:
        """Should return None with no resolvers configured."""
        chained = ChainedPdfResolver([])

        result = chained.resolve({"ArXiv": "2001.12345"})

        assert result is None
