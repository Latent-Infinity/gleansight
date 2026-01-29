from __future__ import annotations

from pathlib import Path

import pytest

from papers.infra.converter_docling.adapter import build_docling_converter

pytestmark = pytest.mark.integration


def _build_pdf_bytes(text: str) -> bytes:
    header = b"%PDF-1.4\n"
    content = f"BT /F1 24 Tf 72 120 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] ",
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj << /Length %d >>\nstream\n" % len(content)
        + content
        + b"\nendstream\nendobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    offsets: list[int] = []
    body = bytearray()
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        body.extend(obj)
        cursor += len(obj)

    xref_offset = cursor
    xref = bytearray()
    xref.extend(b"xref\n")
    xref.extend(f"0 {len(objects) + 1}\n".encode("ascii"))
    xref.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        xref.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    trailer = (
        b"trailer\n"
        + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
        + b"startxref\n"
        + f"{xref_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )

    return header + body + xref + trailer


def test_docling_converts_pdf(tmp_path: Path) -> None:
    pytest.importorskip("docling")
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(_build_pdf_bytes("Hello"))

    converter = build_docling_converter()
    result = converter.pdf_to_markdown(pdf_path)
    assert result.ok
    assert result.markdown
