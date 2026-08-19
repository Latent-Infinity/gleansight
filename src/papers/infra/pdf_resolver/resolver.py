"""PDF URL resolvers for various external ID types."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from papers.app.ports import ResolvedPdf

if TYPE_CHECKING:
    from papers.app.ports import PdfResolver

logger = logging.getLogger(__name__)


def _extract_arxiv_id(external_ids: dict[str, str]) -> str | None:
    """Extract ArXiv ID from external IDs dict (case-insensitive key lookup)."""
    for key, value in external_ids.items():
        if key.lower() == "arxiv":
            return value
    return None


@dataclass
class ArxivExportPdfResolver:
    """Resolves PDF URLs via export.arxiv.org (designed for programmatic access)."""

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        """Resolve ArXiv ID to export.arxiv.org PDF URL.

        Args:
            external_ids: Dict of external ID type to value (e.g., {"ArXiv": "2001.12345"})

        Returns:
            ResolvedPdf with export URL if ArXiv ID found, None otherwise
        """
        arxiv_id = _extract_arxiv_id(external_ids)
        if not arxiv_id:
            return None

        url = f"https://export.arxiv.org/pdf/{arxiv_id}.pdf"
        logger.debug("Resolved ArXiv ID %s to export URL %s", arxiv_id, url)
        return ResolvedPdf(url=url, source="arxiv_export")


@dataclass
class ArxivPdfResolver:
    """Resolves PDF URLs from ArXiv IDs (arxiv.org fallback)."""

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        """Resolve ArXiv ID to PDF URL.

        Args:
            external_ids: Dict of external ID type to value (e.g., {"ArXiv": "2001.12345"})

        Returns:
            ResolvedPdf with URL if ArXiv ID found, None otherwise
        """
        arxiv_id = _extract_arxiv_id(external_ids)
        if not arxiv_id:
            return None

        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        logger.debug("Resolved ArXiv ID %s to URL %s", arxiv_id, url)
        return ResolvedPdf(url=url, source="arxiv")


@dataclass
class UnpaywallPdfResolver:
    """Resolves PDF URLs from DOIs via Unpaywall API."""

    email: str | None = None

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        """Resolve DOI to PDF URL via Unpaywall API.

        Args:
            external_ids: Dict of external ID type to value (e.g., {"DOI": "10.1234/abc"})

        Returns:
            ResolvedPdf with URL if open access PDF found, None otherwise
        """
        if not self.email:
            logger.debug("Unpaywall resolver skipped: no email configured")
            return None

        # Check for DOI (case-insensitive key)
        doi = None
        for key, value in external_ids.items():
            if key.lower() == "doi":
                doi = value
                break

        if not doi:
            return None

        # Query Unpaywall API
        url = f"https://api.unpaywall.org/v2/{doi}?email={self.email}"
        try:
            response = httpx.get(url, timeout=30.0)
            if response.status_code != 200:
                logger.debug(
                    "Unpaywall API returned status %d for DOI %s", response.status_code, doi
                )
                return None

            data = response.json()
            best_oa = data.get("best_oa_location")
            if not best_oa:
                logger.debug("No open access location found for DOI %s", doi)
                return None

            pdf_url = best_oa.get("url_for_pdf")
            if not pdf_url:
                logger.debug("No PDF URL in best OA location for DOI %s", doi)
                return None

            logger.debug("Resolved DOI %s to URL %s via Unpaywall", doi, pdf_url)
            return ResolvedPdf(url=pdf_url, source="unpaywall")

        except httpx.HTTPError as e:
            logger.warning("Unpaywall API error for DOI %s: %s", doi, e)
            return None


@dataclass
class OpenAccessPdfResolver:
    """Resolves PDF URLs from Semantic Scholar openAccessPdf URLs stored in external_ids."""

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        url = external_ids.get("OpenAccessPdf")
        if not url:
            return None
        logger.debug("Resolved open access PDF URL: %s", url)
        return ResolvedPdf(url=url, source="semantic_scholar")


@dataclass
class SemanticScholarPdfResolver:
    """Resolves PDF URLs by querying the Semantic Scholar paper API at download time.

    Uses DOI or CorpusId to look up a paper's openAccessPdf URL via the S2 API.
    This handles papers imported before the OpenAccessPdf key was stored in external_ids.
    """

    api_key: str | None = None
    timeout_s: float = 30.0

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        # Try DOI first, then CorpusId
        identifier = self._get_identifier(external_ids)
        if not identifier:
            return None

        url = f"https://api.semanticscholar.org/graph/v1/paper/{identifier}"
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            response = httpx.get(
                url,
                params={"fields": "openAccessPdf"},
                headers=headers,
                timeout=self.timeout_s,
            )
            if response.status_code != 200:
                logger.debug(
                    "S2 paper API returned status %d for %s", response.status_code, identifier
                )
                return None

            data = response.json()
            oa_pdf = data.get("openAccessPdf")
            if not oa_pdf or not oa_pdf.get("url"):
                logger.debug("No open access PDF found via S2 API for %s", identifier)
                return None

            pdf_url = oa_pdf["url"]
            logger.debug("Resolved %s to PDF URL %s via S2 API", identifier, pdf_url)
            return ResolvedPdf(url=pdf_url, source="semantic_scholar")

        except httpx.HTTPError as e:
            logger.warning("S2 paper API error for %s: %s", identifier, e)
            return None

    @staticmethod
    def _get_identifier(external_ids: dict[str, str]) -> str | None:
        """Build an S2 API paper identifier from external IDs."""
        for key, value in external_ids.items():
            if key.lower() == "doi":
                return f"DOI:{value}"
        for key, value in external_ids.items():
            if key.lower() == "corpusid":
                return f"CorpusID:{value}"
        return None


_MDPI_LINK_PATTERN = re.compile(r"https?://www\.mdpi\.com/[\d-]+/(\d+)/\d+/(\d+)/pdf")


@dataclass
class MdpiPdfResolver:
    """Resolves MDPI PDFs via their CDN, bypassing Akamai bot protection on mdpi.com.

    MDPI's publisher pages are protected by Akamai CDN which blocks all programmatic
    access. Their actual PDFs are served from mdpi-res.com without bot protection.

    Uses CrossRef API (free, no key) to get the journal name and MDPI PDF link,
    then constructs the CDN URL. Only requires a DOI starting with 10.3390/.

    CDN URL pattern:
        https://mdpi-res.com/d_attachment/{journal}/{journal}-{vol}-{art}/article_deploy/{journal}-{vol}-{art}.pdf
    """

    timeout_s: float = 30.0

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        doi = None
        for key, value in external_ids.items():
            if key.lower() == "doi":
                doi = value
                break
        if not doi or not doi.startswith("10.3390/"):
            return None

        # Query CrossRef for journal name and MDPI link (contains volume + article number)
        metadata = self._get_crossref_metadata(doi)
        if metadata is None:
            return None

        journal_name, volume, article = metadata
        journal_lower = journal_name.lower().replace(" ", "")
        article_padded = article.zfill(5)
        cdn_url = (
            f"https://mdpi-res.com/d_attachment/{journal_lower}/"
            f"{journal_lower}-{volume}-{article_padded}/article_deploy/"
            f"{journal_lower}-{volume}-{article_padded}.pdf"
        )
        logger.debug("Resolved MDPI DOI %s to CDN URL %s", doi, cdn_url)
        return ResolvedPdf(url=cdn_url, source="mdpi_cdn")

    def _get_crossref_metadata(self, doi: str) -> tuple[str, str, str] | None:
        """Query CrossRef API for journal name, volume, and article number.

        Returns:
            (journal_name, volume, article_number) or None on failure.
        """
        try:
            response = httpx.get(
                f"https://api.crossref.org/works/{doi}",
                headers={"Accept": "application/json"},
                timeout=self.timeout_s,
            )
            if response.status_code != 200:
                return None
            msg = response.json().get("message", {})

            # Journal name from container-title
            titles = msg.get("container-title", [])
            if not titles:
                return None
            journal_name = titles[0]

            # Volume and article number from the MDPI link URL
            for link in msg.get("link", []):
                match = _MDPI_LINK_PATTERN.search(link.get("URL", ""))
                if match:
                    return journal_name, match.group(1), match.group(2)

            # Fallback: volume from metadata, article from resource URL
            volume = msg.get("volume")
            resource_url = (msg.get("resource") or {}).get("primary", {}).get("URL", "")
            # Resource URL: https://www.mdpi.com/{ISSN}/{volume}/{issue}/{article}
            parts = resource_url.rstrip("/").split("/")
            if volume and len(parts) >= 2:
                article = parts[-1]
                if article.isdigit():
                    return journal_name, str(volume), article

            return None
        except (httpx.HTTPError, KeyError, IndexError):
            logger.warning("CrossRef lookup failed for DOI %s", doi)
            return None


@dataclass
class ChainedPdfResolver:
    """Chains multiple resolvers, trying each in order until one succeeds."""

    resolvers: list[PdfResolver]

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        """Try resolvers in order until one succeeds.

        Args:
            external_ids: Dict of external ID type to value

        Returns:
            ResolvedPdf from first successful resolver, None if all fail
        """
        for resolver in self.resolvers:
            result = resolver.resolve(external_ids)
            if result is not None:
                return result
        return None

    def resolve_all(self, external_ids: dict[str, str]) -> list[ResolvedPdf]:
        """Collect results from all resolvers that succeed.

        Returns:
            List of ResolvedPdf from all successful resolvers, in chain order.
        """
        results: list[ResolvedPdf] = []
        for resolver in self.resolvers:
            result = resolver.resolve(external_ids)
            if result is not None:
                results.append(result)
        return results
