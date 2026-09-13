from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.operator_g_readiness import (
    PREDECESSOR_DIGEST,
    PREDECESSOR_MANIFEST,
    project_zero_readiness,
    readiness_source_bindings,
)
from nsqd.domain.operator_g_types import StructuredValue
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from nsqd.infrastructure.operator_g_census_files import DEFAULT_SCOPE
from tests.nsqd.operator_g_census_support import APPROVED_INPUT_ROOT, census_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_NAME = "nsqd-operator-g-readiness-census-2026-09-12-schema-closure"
OUTPUT_LOGICAL_ROOT = Path(f"docs/reviews/{OUTPUT_NAME}")
PREDECESSOR_NAME = "nsqd-operator-g-readiness-census-2026-09-12-contract-closure"
PREDECESSOR_PACKET_DIGEST = "0649829a742d6433ec757afb5620cfa5f03665372d08196b47259a432bbb3f49"
HISTORICAL_READINESS_SHA256 = "29979cfb2dc23757ebf0c619d6098ac7f0a2a516dd45fc72885cbaf81bb7355e"
HISTORICAL_MANIFEST_SHA256 = "2e9f3f28e8c70bb44e5a4d0797838ed4e1dee18a631680c663560c7ef30e1dcf"
HISTORICAL_PACKET_DIGEST = "9af4910deb08b980a6a8ee0feda263825cada46703b13d54e00aeb983ea06680"


def _json(path: Path) -> dict[str, StructuredValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_current_census_uses_only_positive_input_scope() -> None:
    assert DEFAULT_SCOPE.roots == (APPROVED_INPUT_ROOT,)


def test_live_readiness_binds_contracts_and_implementation_not_generated_reports() -> None:
    bindings = readiness_source_bindings(REPO_ROOT)
    paths = {binding.path for binding in bindings}

    assert "evidence/contracts/nsqd/operator-g/v1/failure-record-contract.yaml" in paths
    assert "evidence/contracts/nsqd/operator-g/v2/failure-record-contract-v2.yaml" in paths
    assert not any(path.startswith("docs/") or path.startswith("output/") for path in paths)


def test_live_projection_is_scoped_complete_zero_without_authority() -> None:
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())
    projection = project_zero_readiness(census, readiness_source_bindings(REPO_ROOT))

    assert PREDECESSOR_MANIFEST == f"../{PREDECESSOR_NAME}/packet-manifest.json"
    assert PREDECESSOR_DIGEST == PREDECESSOR_PACKET_DIGEST
    assert census.scope_file_count == 0
    assert census.qualifying_record_digests == ()
    assert projection["records"] == []
    projected_census = projection["census"]
    authority = projection["authority"]
    assert isinstance(projected_census, dict)
    assert isinstance(authority, dict)
    assert projected_census["input_scope"] == {
        "kind": "versioned_evidence_roots",
        "roots": [APPROVED_INPUT_ROOT],
    }
    assert all(value is False for value in authority.values())


def test_historical_broad_scope_packet_remains_immutable() -> None:
    output_root = resolve_artifact_path(REPO_ROOT, OUTPUT_LOGICAL_ROOT)
    readiness_path = output_root / "readiness.json"
    manifest_path = output_root / "packet-manifest.json"
    readiness = _json(readiness_path)
    manifest = _json(manifest_path)
    historical_census = readiness["census"]

    assert isinstance(historical_census, dict)
    assert historical_census["repository_roots"] == ["docs", "src", "tests"]
    assert historical_census["scope_file_count"] == 354
    assert historical_census["scope_snapshot_digest"] == (
        "b930b81be31ebdad3e9007c6b96963939dc73915da6a896f8914ba9e3b2abbb4"
    )
    assert hashlib.sha256(readiness_path.read_bytes()).hexdigest() == HISTORICAL_READINESS_SHA256
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == HISTORICAL_MANIFEST_SHA256
    assert manifest["packet_digest"] == HISTORICAL_PACKET_DIGEST
