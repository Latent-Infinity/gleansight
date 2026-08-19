"""PDF resolver infrastructure for resolving and downloading PDFs."""

from papers.infra.pdf_resolver.downloader import PdfDownloader
from papers.infra.pdf_resolver.resolver import (
    ArxivExportPdfResolver,
    ArxivPdfResolver,
    ChainedPdfResolver,
    MdpiPdfResolver,
    OpenAccessPdfResolver,
    SemanticScholarPdfResolver,
    UnpaywallPdfResolver,
)

__all__ = [
    "ArxivExportPdfResolver",
    "ArxivPdfResolver",
    "ChainedPdfResolver",
    "MdpiPdfResolver",
    "OpenAccessPdfResolver",
    "PdfDownloader",
    "SemanticScholarPdfResolver",
    "UnpaywallPdfResolver",
]
