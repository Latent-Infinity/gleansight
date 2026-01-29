from __future__ import annotations

from pathlib import Path

from papers.infra.blobs_fs.store import FileSystemBlobStore


def test_put_pdf_and_get_path(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    store = FileSystemBlobStore(root)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"pdf")
    pdf_xxh64, stored = store.put_pdf(pdf_path)
    assert stored.exists()
    assert store.get_pdf_path(pdf_xxh64) == stored


def test_put_markdown(tmp_path: Path) -> None:
    store = FileSystemBlobStore(tmp_path / "blobs")
    path, md_xxh64 = store.put_markdown("paper", "hello")
    assert path.exists()
    assert md_xxh64


def test_put_analysis_artifacts(tmp_path: Path) -> None:
    store = FileSystemBlobStore(tmp_path / "blobs")
    paths = store.put_analysis_artifacts("run", "out", {"a": 1}, {"m": 2})
    assert (tmp_path / "blobs" / "analysis" / "run" / "output.md").exists()
    assert "output_json" in paths
