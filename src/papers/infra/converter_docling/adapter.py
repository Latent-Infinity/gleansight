from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from papers.app import ports
from papers.domain.errors import ErrorCode, PipelineError


@dataclass(frozen=True)
class DoclingConverter(ports.Converter):
    convert_func: Callable[[Path], str]
    version_str: str

    def pdf_to_markdown(self, pdf_path: Path) -> ports.ConverterResult:
        try:
            markdown = self.convert_func(pdf_path)
        except Exception as exc:
            return ports.ConverterResult(
                ok=False,
                markdown=None,
                error_code=ErrorCode.CONVERSION_FAILED,
                error_message=str(exc),
            )
        if not markdown.strip():
            return ports.ConverterResult(
                ok=False,
                markdown=None,
                error_code=ErrorCode.EMPTY_OUTPUT,
                error_message="converter returned empty output",
            )
        return ports.ConverterResult(
            ok=True,
            markdown=markdown,
            error_code=None,
            error_message=None,
        )

    def version(self) -> str:
        return self.version_str


def build_docling_converter() -> DoclingConverter:
    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:  # pragma: no cover - optional dependency
        raise PipelineError(ErrorCode.CONVERSION_FAILED, "docling not installed") from exc

    format_options = None
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import ThreadedPdfPipelineOptions
        from docling.document_converter import PdfFormatOption
        from docling.pipeline.threaded_standard_pdf_pipeline import ThreadedStandardPdfPipeline

        pipeline_options = ThreadedPdfPipelineOptions(generate_page_images=True)
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=ThreadedStandardPdfPipeline,
                pipeline_options=pipeline_options,
            )
        }
    except Exception:
        format_options = None

    try:
        converter = DocumentConverter(format_options=format_options)
    except TypeError:
        converter = DocumentConverter()

    def _convert(path: Path) -> str:
        result = converter.convert(path)
        return result.document.export_to_markdown()

    version = getattr(converter, "__version__", "unknown")
    return DoclingConverter(convert_func=_convert, version_str=version)
