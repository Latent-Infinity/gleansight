from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from research.catalog.models import CatalogError
from research.catalog.verify import verify_bundle
from tests.research.test_capacity_verification import verified_fixture as verified_fixture


@pytest.mark.parametrize(
    "mutation",
    ["extra", "missing", "hash", "manifest_keys", "schema", "workflow", "missing_field", "symlink"],
)
def test_malformed_or_spoofed_artifacts_refuse_verification(
    verified_fixture: Path, tmp_path: Path, mutation: str
) -> None:
    bundle = tmp_path / "candidate"
    shutil.copytree(verified_fixture, bundle)
    metadata_path = bundle / "run-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    if mutation == "extra":
        (bundle / "unexpected.json").write_text("{}")
    elif mutation == "missing":
        (bundle / "report.md").unlink()
    elif mutation == "hash":
        (bundle / "report.md").write_text("forged")
    elif mutation == "manifest_keys":
        metadata["artifact_sha256"].pop("report.md")
    elif mutation == "schema":
        metadata["schema_version"] = 9
    elif mutation == "workflow":
        metadata["workflow"] = "financial-jepa-walkforward-preregistration"
    elif mutation == "missing_field":
        path = bundle / "document.json"
        document = json.loads(path.read_text())
        document.pop("protocol")
        path.write_text(json.dumps(document))
        metadata["artifact_sha256"]["document.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation == "symlink":
        (bundle / "report.md").unlink()
        (bundle / "report.md").symlink_to(verified_fixture / "report.md")
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises((CatalogError, ValueError)):
        verify_bundle(bundle)
