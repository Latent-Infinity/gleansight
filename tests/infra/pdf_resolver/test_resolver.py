"""Tests for PDF resolvers."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from papers.app.ports import ResolvedPdf
from papers.infra.pdf_resolver.resolver import (
    ArxivExportPdfResolver,
    ArxivPdfResolver,
    ChainedPdfResolver,
    MdpiPdfResolver,
    OpenAccessPdfResolver,
    SemanticScholarPdfResolver,
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


class TestArxivExportPdfResolver:
    """Tests for ArxivExportPdfResolver."""

    def test_resolve_with_arxiv_id(self) -> None:
        """Should return export.arxiv.org PDF URL when ArXiv ID is present."""
        resolver = ArxivExportPdfResolver()
        external_ids = {"ArXiv": "2001.12345"}

        result = resolver.resolve(external_ids)

        assert result is not None
        assert result.url == "https://export.arxiv.org/pdf/2001.12345.pdf"
        assert result.source == "arxiv_export"

    def test_resolve_returns_none_without_arxiv_id(self) -> None:
        """Should return None when no ArXiv ID is present."""
        resolver = ArxivExportPdfResolver()
        external_ids = {"DOI": "10.1234/abc"}

        result = resolver.resolve(external_ids)

        assert result is None

    def test_resolve_returns_none_with_empty_dict(self) -> None:
        """Should return None for empty external IDs."""
        resolver = ArxivExportPdfResolver()

        result = resolver.resolve({})

        assert result is None

    def test_resolve_with_version_suffix(self) -> None:
        """Should handle ArXiv IDs with version suffix."""
        resolver = ArxivExportPdfResolver()
        external_ids = {"ArXiv": "2001.12345v2"}

        result = resolver.resolve(external_ids)

        assert result is not None
        assert result.url == "https://export.arxiv.org/pdf/2001.12345v2.pdf"


class TestOpenAccessPdfResolver:
    """Tests for OpenAccessPdfResolver."""

    def test_resolve_with_open_access_url(self) -> None:
        resolver = OpenAccessPdfResolver()
        external_ids = {"DOI": "10.1234/abc", "OpenAccessPdf": "https://example.com/paper.pdf"}

        result = resolver.resolve(external_ids)

        assert result is not None
        assert result.url == "https://example.com/paper.pdf"
        assert result.source == "semantic_scholar"

    def test_resolve_returns_none_without_url(self) -> None:
        resolver = OpenAccessPdfResolver()
        external_ids = {"DOI": "10.1234/abc", "ArXiv": "2001.12345"}

        result = resolver.resolve(external_ids)

        assert result is None

    def test_resolve_returns_none_with_empty_dict(self) -> None:
        resolver = OpenAccessPdfResolver()

        result = resolver.resolve({})

        assert result is None


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


class TestSemanticScholarPdfResolver:
    """Tests for SemanticScholarPdfResolver."""

    def test_resolve_returns_none_without_doi_or_corpusid(self) -> None:
        """Should return None when no DOI or CorpusId is present."""
        resolver = SemanticScholarPdfResolver()
        external_ids = {"ArXiv": "2001.12345", "PubMed": "12345678"}

        result = resolver.resolve(external_ids)

        assert result is None

    def test_resolve_returns_none_with_empty_dict(self) -> None:
        """Should return None for empty external IDs."""
        resolver = SemanticScholarPdfResolver()

        result = resolver.resolve({})

        assert result is None

    def test_get_identifier_prefers_doi(self) -> None:
        """Should prefer DOI over CorpusId."""
        result = SemanticScholarPdfResolver._get_identifier(
            {"DOI": "10.1234/abc", "CorpusId": "12345"}
        )
        assert result == "DOI:10.1234/abc"

    def test_get_identifier_falls_back_to_corpusid(self) -> None:
        """Should use CorpusId when DOI is not available."""
        result = SemanticScholarPdfResolver._get_identifier({"CorpusId": "12345"})
        assert result == "CorpusID:12345"

    def test_get_identifier_case_insensitive(self) -> None:
        """Should handle case-insensitive keys."""
        result = SemanticScholarPdfResolver._get_identifier({"doi": "10.1234/abc"})
        assert result == "DOI:10.1234/abc"

        result = SemanticScholarPdfResolver._get_identifier({"corpusid": "12345"})
        assert result == "CorpusID:12345"

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_with_doi_success(self, mock_get: object) -> None:
        """Should return PDF URL when S2 API returns openAccessPdf."""
        mock_response = httpx.Response(
            200,
            json={"openAccessPdf": {"url": "https://example.com/paper.pdf", "status": "GREEN"}},
            request=httpx.Request(
                "GET", "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/abc"
            ),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = SemanticScholarPdfResolver()
        result = resolver.resolve({"DOI": "10.1234/abc"})

        assert result is not None
        assert result.url == "https://example.com/paper.pdf"
        assert result.source == "semantic_scholar"

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_with_corpusid_success(self, mock_get: object) -> None:
        """Should resolve using CorpusId when DOI is absent."""
        mock_response = httpx.Response(
            200,
            json={"openAccessPdf": {"url": "https://example.com/paper2.pdf", "status": "GREEN"}},
            request=httpx.Request(
                "GET", "https://api.semanticscholar.org/graph/v1/paper/CorpusID:99999"
            ),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = SemanticScholarPdfResolver()
        result = resolver.resolve({"CorpusId": "99999"})

        assert result is not None
        assert result.url == "https://example.com/paper2.pdf"

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_returns_none_when_no_open_access(self, mock_get: object) -> None:
        """Should return None when S2 API returns no openAccessPdf."""
        mock_response = httpx.Response(
            200,
            json={"openAccessPdf": None},
            request=httpx.Request(
                "GET", "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/abc"
            ),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = SemanticScholarPdfResolver()
        result = resolver.resolve({"DOI": "10.1234/abc"})

        assert result is None

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_returns_none_on_404(self, mock_get: object) -> None:
        """Should return None when S2 API returns 404."""
        mock_response = httpx.Response(
            404,
            json={"error": "Paper not found"},
            request=httpx.Request(
                "GET", "https://api.semanticscholar.org/graph/v1/paper/DOI:10.9999/missing"
            ),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = SemanticScholarPdfResolver()
        result = resolver.resolve({"DOI": "10.9999/missing"})

        assert result is None

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_returns_none_on_http_error(self, mock_get: object) -> None:
        """Should return None on network errors."""
        mock_get.side_effect = httpx.ConnectError("connection refused")  # type: ignore[attr-defined]

        resolver = SemanticScholarPdfResolver()
        result = resolver.resolve({"DOI": "10.1234/abc"})

        assert result is None

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_passes_api_key(self, mock_get: object) -> None:
        """Should include x-api-key header when api_key is set."""
        mock_response = httpx.Response(
            200,
            json={"openAccessPdf": {"url": "https://example.com/paper.pdf", "status": "GREEN"}},
            request=httpx.Request(
                "GET", "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/abc"
            ),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = SemanticScholarPdfResolver(api_key="test-key-123")
        resolver.resolve({"DOI": "10.1234/abc"})

        call_kwargs = mock_get.call_args  # type: ignore[attr-defined]
        assert call_kwargs.kwargs["headers"]["x-api-key"] == "test-key-123"


class TestMdpiPdfResolver:
    """Tests for MdpiPdfResolver."""

    def test_resolve_returns_none_for_non_mdpi_doi(self) -> None:
        """Should return None when DOI is not from MDPI (10.3390/)."""
        resolver = MdpiPdfResolver()
        result = resolver.resolve({"DOI": "10.1234/abc"})
        assert result is None

    def test_resolve_returns_none_without_doi(self) -> None:
        """Should return None when no DOI is present."""
        resolver = MdpiPdfResolver()
        result = resolver.resolve({"ArXiv": "2001.12345"})
        assert result is None

    def test_resolve_returns_none_with_empty_dict(self) -> None:
        """Should return None for empty external IDs."""
        resolver = MdpiPdfResolver()
        result = resolver.resolve({})
        assert result is None

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_constructs_cdn_url_from_crossref_link(self, mock_get: object) -> None:
        """Construct CDN URL from CrossRef link and journal name."""
        mock_response = httpx.Response(
            200,
            json={
                "message": {
                    "container-title": ["Mathematics"],
                    "link": [
                        {
                            "URL": "https://www.mdpi.com/2227-7390/10/12/2128/pdf",
                            "content-type": "unspecified",
                        }
                    ],
                }
            },
            request=httpx.Request("GET", "https://api.crossref.org/works/10.3390/math10122128"),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = MdpiPdfResolver()
        result = resolver.resolve({"DOI": "10.3390/math10122128"})

        assert result is not None
        assert result.url == (
            "https://mdpi-res.com/d_attachment/mathematics/"
            "mathematics-10-02128/article_deploy/mathematics-10-02128.pdf"
        )
        assert result.source == "mdpi_cdn"

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_uses_resource_url_fallback(self, mock_get: object) -> None:
        """Should fall back to resource URL + volume when link field has no MDPI URL."""
        mock_response = httpx.Response(
            200,
            json={
                "message": {
                    "container-title": ["Mathematics"],
                    "volume": 10,
                    "link": [],
                    "resource": {"primary": {"URL": "https://www.mdpi.com/2227-7390/10/12/2128"}},
                }
            },
            request=httpx.Request("GET", "https://api.crossref.org/works/10.3390/math10122128"),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = MdpiPdfResolver()
        result = resolver.resolve({"DOI": "10.3390/math10122128"})

        assert result is not None
        assert result.url == (
            "https://mdpi-res.com/d_attachment/mathematics/"
            "mathematics-10-02128/article_deploy/mathematics-10-02128.pdf"
        )

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_returns_none_when_crossref_fails(self, mock_get: object) -> None:
        """Should return None when CrossRef API fails."""
        mock_get.side_effect = httpx.ConnectError("connection refused")  # type: ignore[attr-defined]

        resolver = MdpiPdfResolver()
        result = resolver.resolve({"DOI": "10.3390/math10122128"})

        assert result is None

    @patch("papers.infra.pdf_resolver.resolver.httpx.get")
    def test_resolve_returns_none_when_no_journal_name(self, mock_get: object) -> None:
        """Should return None when CrossRef response has no container-title."""
        mock_response = httpx.Response(
            200,
            json={"message": {"container-title": [], "link": []}},
            request=httpx.Request("GET", "https://api.crossref.org/works/10.3390/math10122128"),
        )
        mock_get.return_value = mock_response  # type: ignore[attr-defined]

        resolver = MdpiPdfResolver()
        result = resolver.resolve({"DOI": "10.3390/math10122128"})

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

    def test_resolve_all_returns_all_successful(self) -> None:
        """Should return results from all resolvers that succeed."""

        class FakeResolver:
            def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
                return ResolvedPdf(url="https://fake.com/pdf", source="fake")

        chained = ChainedPdfResolver([ArxivPdfResolver(), OpenAccessPdfResolver(), FakeResolver()])

        results = chained.resolve_all(
            {"ArXiv": "2001.12345", "OpenAccessPdf": "https://oa.com/paper.pdf"}
        )

        assert len(results) == 3
        assert results[0].source == "arxiv"
        assert results[1].source == "semantic_scholar"
        assert results[2].source == "fake"

    def test_resolve_all_skips_failures(self) -> None:
        """Should skip resolvers that return None."""
        chained = ChainedPdfResolver([ArxivPdfResolver(), OpenAccessPdfResolver()])

        # No ArXiv ID, no OpenAccessPdf — both should fail
        results = chained.resolve_all({"DOI": "10.1234/abc"})

        assert len(results) == 0

    def test_resolve_all_empty_resolvers(self) -> None:
        """Should return empty list with no resolvers configured."""
        chained = ChainedPdfResolver([])

        results = chained.resolve_all({"ArXiv": "2001.12345"})

        assert results == []
