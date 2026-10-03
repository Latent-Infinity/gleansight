from __future__ import annotations

from pathlib import Path

from research.catalog.verify import verify_bundle
from tests.research.catalog_fixtures import baseline_bundle


def test_original_yieldjepa_source_hash_convention_is_verified_without_claiming_paired_dates(
    tmp_path: Path,
) -> None:
    path = baseline_bundle(tmp_path)
    run = verify_bundle(path)
    assert run.classification == "smoke" and run.verification == "artifact_hashes"
    assert run.date_sha256 and not run.origin_dates
    assert len(run.metrics) == 6
    assert any("not reconstructed" in limitation for limitation in run.limitations)
