from __future__ import annotations

import hashlib
import json
from pathlib import Path

from gleansight.api import GleansightAPI
from gleansight.api.runtime import ApiConfiguration
from tests.research.test_capacity_verification import verified_fixture as verified_fixture
from tests.research.test_catalog_storage import owned_pair


def test_public_catalog_operations_emit_verified_separate_comparison(
    verified_fixture: Path, tmp_path: Path
) -> None:
    paths = owned_pair(tmp_path, verified_fixture)
    original = {str(file): file.read_bytes() for path in paths for file in path.iterdir()}
    api = GleansightAPI(ApiConfiguration(repo_root=tmp_path))
    indexed = []
    for path in paths:
        payload = {"bundle_path": str(path.relative_to(tmp_path))}
        verified = api.call("research.runs.verify", payload)
        assert verified.status == "ok"
        result = api.call("research.runs.index", payload).model_dump(mode="json")
        assert result["status"] == "ok"
        indexed.append(result["data"]["run_id"])
    listing = api.call("research.runs.list", {}).model_dump(mode="json")
    assert len(listing["data"]["runs"]) == 2
    response = api.call("research.runs.compare", {"run_ids": indexed}).model_dump(mode="json")
    assert response["status"] == "ok"
    report = response["data"]["comparison"]
    assert report["comparable"] and report["winner"] is None and len(report["pairs"]) == 18
    artifact = tmp_path / response["data"]["bundle_path"]
    assert artifact.is_relative_to(tmp_path / "output/research-comparison")
    assert json.loads((artifact / "comparison.json").read_text()) == report
    manifest = json.loads((artifact / "manifest.json").read_text())
    assert manifest == {
        name: hashlib.sha256((artifact / name).read_bytes()).hexdigest()
        for name in ("comparison.json", "report.md")
    }
    assert original == {name: Path(name).read_bytes() for name in original}
    (paths[0] / "report.md").write_text("changed")
    stale = api.call("research.runs.list", {}).model_dump(mode="json")
    assert sum(not item["verified"] for item in stale["data"]["runs"]) == 1
    assert api.call("research.runs.compare", {"run_ids": indexed}).status == "error"
    assert api.call("research.runs.list", {"limit": 101}).status == "error"
