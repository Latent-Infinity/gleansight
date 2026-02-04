"""PDF URL resolvers for various external ID types."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from papers.app.ports import ResolvedPdf

if TYPE_CHECKING:
    from papers.app.ports import PdfResolver

logger = logging.getLogger(__name__)


@dataclass
class ArxivPdfResolver:
    """Resolves PDF URLs from ArXiv IDs."""

    def resolve(self, external_ids: dict[str, str]) -> ResolvedPdf | None:
        """Resolve ArXiv ID to PDF URL.

        Args:
            external_ids: Dict of external ID type to value (e.g., {"ArXiv": "2001.12345"})

        Returns:
            ResolvedPdf with URL if ArXiv ID found, None otherwise
        """
        # Check for ArXiv ID (case-insensitive key)
        arxiv_id = None
        for key, value in external_ids.items():
            if key.lower() == "arxiv":
                arxiv_id = value
                break

        if not arxiv_id:
            return None

        # ArXiv PDF URLs follow pattern: https://arxiv.org/pdf/{id}.pdf
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
                logger.debug("Unpaywall API returned status %d for DOI %s", response.status_code, doi)
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
