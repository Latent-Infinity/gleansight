from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from papers.domain.ideation import EvidenceMap
from papers.domain.ideation_bundle import BundleIntegrityError, BundleType, verify_manifest


def _evidence_payload() -> dict:
    quote = "hello"
    return {
        "project_id": "project-1",
        "project_name": "Project",
        "inventory": [
            {
                "paper_id": "paper-1",
                "title": "Paper One",
                "markdown_missing": False,
                "partial": True,
                "markdown_bytes": 20,
                "selected_bytes": len(quote.encode()),
                "selected_excerpt_ids": ["paper-1:e001"],
            }
        ],
        "excerpts": [
            {
                "excerpt_id": "paper-1:e001",
                "paper_id": "paper-1",
                "title": "Paper One",
                "section": "Abstract",
                "byte_start": 0,
                "byte_end": len(quote.encode()),
                "sha256": hashlib.sha256(quote.encode()).hexdigest(),
                "quote": quote,
            }
        ],
        "coverage_note": "Only selected excerpts were analyzed.",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("paper_id", "paper-2"),
        ("title", "Wrong paper"),
        ("excerpt_id", "paper-1:e002"),
    ],
)
def test_evidence_map_rejects_excerpt_inventory_mismatch(field: str, value: str) -> None:
    payload = _evidence_payload()
    payload["excerpts"][0][field] = value

    with pytest.raises(ValidationError, match="inventory"):
        EvidenceMap.model_validate(payload)


def test_manifest_rejects_unlisted_bundle_entry(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    artifact_names = (
        "evidence-map.json",
        "ideas.json",
        "critique.json",
        "provenance.json",
        "report.md",
    )
    manifest: dict[str, str] = {}
    for name in artifact_names:
        path = bundle / name
        path.write_text("content")
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (bundle / "unlisted.json").write_text("not manifest-bound")

    with pytest.raises(BundleIntegrityError, match="artifact set"):
        verify_manifest(bundle, BundleType.project_ideation)


def test_manifest_rejects_symlinked_artifact(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("outside")
    artifact_names = (
        "evidence-map.json",
        "ideas.json",
        "critique.json",
        "provenance.json",
        "report.md",
    )
    manifest: dict[str, str] = {}
    for name in artifact_names:
        path = bundle / name
        if name == "evidence-map.json":
            path.symlink_to(target)
        else:
            path.write_text("content")
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(BundleIntegrityError, match="regular file"):
        verify_manifest(bundle, BundleType.project_ideation)


def test_manifest_rejects_symlinked_bundle_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    bundle = tmp_path / "bundle"
    bundle.symlink_to(target, target_is_directory=True)

    with pytest.raises(BundleIntegrityError, match="regular directory"):
        verify_manifest(bundle, BundleType.project_ideation)
