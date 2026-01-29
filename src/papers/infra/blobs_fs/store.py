from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import xxhash

from papers.app import ports

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class BlobPaths:
    root: Path
    pdf_dir: Path
    md_dir: Path
    analysis_dir: Path


class FileSystemBlobStore(ports.BlobStore):
    def __init__(self, root: Path) -> None:
        self._paths = BlobPaths(
            root=root,
            pdf_dir=root / "pdf",
            md_dir=root / "md",
            analysis_dir=root / "analysis",
        )
        self._paths.pdf_dir.mkdir(parents=True, exist_ok=True)
        self._paths.md_dir.mkdir(parents=True, exist_ok=True)
        self._paths.analysis_dir.mkdir(parents=True, exist_ok=True)

    def put_pdf(self, src_path: Path) -> tuple[str, Path]:
        pdf_xxh64 = _hash_file(src_path)
        dest_path = self._paths.pdf_dir / f"{pdf_xxh64}.pdf"
        if not dest_path.exists():
            _atomic_copy(src_path, dest_path)
        return pdf_xxh64, dest_path

    def get_pdf_path(self, pdf_xxh64: str) -> Path | None:
        path = self._paths.pdf_dir / f"{pdf_xxh64}.pdf"
        return path if path.exists() else None

    def put_markdown(self, paper_id: str, markdown: str) -> tuple[Path, str]:
        md_xxh64 = _hash_text(markdown)
        dest_path = self._paths.md_dir / f"{paper_id}.md"
        _atomic_write_text(dest_path, markdown)
        return dest_path, md_xxh64

    def get_markdown_path(self, paper_id: str) -> Path | None:
        path = self._paths.md_dir / f"{paper_id}.md"
        return path if path.exists() else None

    def put_analysis_artifacts(
        self,
        run_id: str,
        output_md: str,
        output_json: dict | None,
        meta_json: dict,
    ) -> dict[str, Path]:
        run_dir = self._paths.analysis_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        output_md_path = run_dir / "output.md"
        meta_path = run_dir / "meta.json"
        _atomic_write_text(output_md_path, output_md)
        _atomic_write_text(meta_path, json.dumps(meta_json, indent=2, sort_keys=True))
        paths: dict[str, Path] = {"output_md": output_md_path, "meta": meta_path}
        if output_json is not None:
            output_json_path = run_dir / "output.json"
            _atomic_write_text(output_json_path, json.dumps(output_json, indent=2, sort_keys=True))
            paths["output_json"] = output_json_path
        return paths


def _hash_file(path: Path) -> str:
    hasher = xxhash.xxh64()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def _hash_text(text: str) -> str:
    return xxhash.xxh64(text.encode("utf-8")).hexdigest()


def _atomic_write_text(dest: Path, content: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_suffix(dest.suffix + f".{os.getpid()}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(dest)


def _atomic_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_suffix(dest.suffix + f".{os.getpid()}.tmp")
    with src.open("rb") as src_handle, temp_path.open("wb") as dst_handle:
        while chunk := src_handle.read(_CHUNK_SIZE):
            dst_handle.write(chunk)
    temp_path.replace(dest)
