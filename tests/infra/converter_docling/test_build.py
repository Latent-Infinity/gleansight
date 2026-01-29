from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

from papers.infra.converter_docling.adapter import build_docling_converter


def test_build_docling_converter() -> None:
    """Test that build_docling_converter returns a working converter."""
    pytest.importorskip("docling")
    converter = build_docling_converter()
    assert converter.version() is not None
    # Just verify the converter was built successfully
    assert converter.convert_func is not None


def test_build_docling_converter_with_fake() -> None:
    """Test build_docling_converter with fake docling module."""

    class FakeDocument:
        def export_to_markdown(self) -> str:
            return "# Fake Document\n\nContent here"

    class FakeResult:
        def __init__(self) -> None:
            self.document = FakeDocument()

    class FakeDocumentConverter:
        __version__ = "1.2.3"

        def convert(self, path: Path) -> FakeResult:
            return FakeResult()

    fake_docling = types.ModuleType("docling")
    fake_document_converter_module = types.ModuleType("document_converter")

    fake_docling_any = cast(Any, fake_docling)
    fake_doc_conv_any = cast(Any, fake_document_converter_module)
    fake_doc_conv_any.DocumentConverter = FakeDocumentConverter

    # Set up the module hierarchy
    fake_docling_any.document_converter = fake_document_converter_module

    sys.modules["docling"] = fake_docling
    sys.modules["docling.document_converter"] = fake_document_converter_module

    try:
        converter = build_docling_converter()
        assert converter.version_str == "1.2.3"

        # Test the convert function
        result = converter.pdf_to_markdown(Path("/fake/path.pdf"))
        assert result.ok is True
        assert result.markdown == "# Fake Document\n\nContent here"
    finally:
        # Clean up
        if "docling" in sys.modules:
            del sys.modules["docling"]
        if "docling.document_converter" in sys.modules:
            del sys.modules["docling.document_converter"]
