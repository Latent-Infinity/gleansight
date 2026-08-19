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


def test_pdf_fingerprint_is_deterministic(tmp_path: Path) -> None:
    store = FileSystemBlobStore(tmp_path / "blobs")
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"identical-pdf-bytes")
    second.write_bytes(b"identical-pdf-bytes")

    first_hash, first_path = store.put_pdf(first)
    second_hash, second_path = store.put_pdf(second)

    assert first_hash == second_hash
    assert first_path == second_path
    assert first_path.name == f"{first_hash}.pdf"


def test_atomic_markdown_write_replaces_without_temp_leftovers(tmp_path: Path) -> None:
    store = FileSystemBlobStore(tmp_path / "blobs")
    path, _ = store.put_markdown("paper", "hello")
    assert path.read_text(encoding="utf-8") == "hello"

    replaced, _ = store.put_markdown("paper", "world")
    assert replaced == path
    assert path.read_text(encoding="utf-8") == "world"
    assert list(path.parent.glob("*.tmp")) == []
