from __future__ import annotations

from pathlib import Path

from papers.app.ports import ConverterResult
from papers.domain.errors import ErrorCode
from papers.infra.converter_docling.adapter import DoclingConverter


def test_empty_markdown_returns_empty_output(tmp_path: Path) -> None:
    converter = DoclingConverter(convert_func=lambda _: "  \n\t", version_str="1")
    result = converter.pdf_to_markdown(tmp_path / "empty.pdf")
    assert isinstance(result, ConverterResult)
    assert result.ok is False
    assert result.markdown is None
    assert result.error_code == ErrorCode.EMPTY_OUTPUT


def test_converter_exception_returns_conversion_failed(tmp_path: Path) -> None:
    def _boom(_: Path) -> str:
        raise RuntimeError("boom")

    converter = DoclingConverter(convert_func=_boom, version_str="1")
    result = converter.pdf_to_markdown(tmp_path / "broken.pdf")
    assert isinstance(result, ConverterResult)
    assert result.ok is False
    assert result.markdown is None
    assert result.error_code == ErrorCode.CONVERSION_FAILED
