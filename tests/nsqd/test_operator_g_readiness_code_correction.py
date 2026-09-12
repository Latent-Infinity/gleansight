from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nsqd.domain.operator_g_readiness import (
    PREDECESSOR_DIGEST,
    PREDECESSOR_MANIFEST,
    project_zero_readiness,
    readiness_source_bindings,
)
from nsqd.domain.operator_g_types import StructuredValue
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from nsqd.infrastructure.operator_g_census_files import DEFAULT_LIMITS, OUTPUT_DIRECTORIES, discover
from tests.nsqd.operator_g_census_support import census_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_NAME = "nsqd-operator-g-readiness-census-2026-09-12-schema-closure"
OUTPUT_ROOT = REPO_ROOT / "docs" / "reviews" / OUTPUT_NAME
PREDECESSOR_NAME = "nsqd-operator-g-readiness-census-2026-09-12-contract-closure"
PREDECESSOR_PACKET_DIGEST = "0649829a742d6433ec757afb5620cfa5f03665372d08196b47259a432bbb3f49"
IMMUTABLE_ACTIVATION_G_BINDING = "nsqd-operator-g-readiness-census-2026-09-09-c-review-correction"
SUCCESSOR_ROOTS = (
    "nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction",
    "nsqd-operator-f-readiness-2026-09-11-formula-correction",
    "nsqd-status-window-calendar-replay-2026-09-11-command-sync",
    "nsqd-operator-activation-2026-09-11-remediation",
    "nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup",
    "nsqd-operator-f-readiness-2026-09-12-implementation-binding",
    "nsqd-operator-activation-2026-09-12-pointer-sync",
)


def _json(path: Path) -> dict[str, StructuredValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_final_output_is_the_only_new_exact_census_exclusion() -> None:
    assert OUTPUT_DIRECTORIES == frozenset({f"docs/reviews/{OUTPUT_NAME}"})


def test_live_scope_includes_successors_and_detached_technical_reviews() -> None:
    files, issues = discover(REPO_ROOT, limits=DEFAULT_LIMITS)
    paths = {item.path for item in files}

    assert issues == []
    for root in SUCCESSOR_ROOTS:
        assert f"docs/reviews/{root}/packet-manifest.json" in paths
        assert f"docs/reviews/{root}/technical-review-summary.json" in paths
        assert f"docs/reviews/{root}/technical-review-seal.json" in paths
    assert f"docs/reviews/{PREDECESSOR_NAME}/readiness.json" in paths
    assert f"docs/reviews/{PREDECESSOR_NAME}/packet-manifest.json" in paths
    assert not any(path.startswith(f"docs/reviews/{OUTPUT_NAME}/") for path in paths)


def test_live_projection_binds_current_sources_and_predecessor_without_authority() -> None:
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())
    bindings = readiness_source_bindings(REPO_ROOT)
    projection = project_zero_readiness(census, bindings)
    paths = {binding.path for binding in bindings}

    assert PREDECESSOR_MANIFEST == f"../{PREDECESSOR_NAME}/packet-manifest.json"
    assert PREDECESSOR_DIGEST == PREDECESSOR_PACKET_DIGEST
    for root in SUCCESSOR_ROOTS:
        assert f"docs/reviews/{root}/packet-manifest.json" in paths
        assert f"docs/reviews/{root}/technical-review-summary.json" in paths
        assert f"docs/reviews/{root}/technical-review-seal.json" in paths
    assert f"docs/reviews/{PREDECESSOR_NAME}/readiness.json" in paths
    assert f"docs/reviews/{PREDECESSOR_NAME}/packet-manifest.json" in paths
    assert census.status.value == "complete"
    assert census.trusted_approval_count == 0
    assert census.trusted_evidence_artifact_count == 0
    assert census.qualifying_record_digests == ()
    assert projection["records"] == []
    authority = projection["authority"]
    assert isinstance(authority, dict)
    assert all(value is False for value in authority.values())


def test_final_packet_replays_and_current_markdown_pointers_are_synchronized() -> None:
    readiness = _json(OUTPUT_ROOT / "readiness.json")
    manifest = _json(OUTPUT_ROOT / "packet-manifest.json")
    readiness_sha256 = hashlib.sha256((OUTPUT_ROOT / "readiness.json").read_bytes()).hexdigest()
    artifacts = {"readiness.json": readiness_sha256}
    packet_digest = hashlib.sha256(
        json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert readiness == project_zero_readiness(
        census_operator_g_evidence(REPO_ROOT, contract=census_contract()),
        readiness_source_bindings(REPO_ROOT),
    )
    assert manifest == {
        "artifact_sha256": artifacts,
        "packet_digest": packet_digest,
        "schema_version": 1,
    }
    for relative in (
        "docs/development-plan-ns-qd.md",
        "docs/evidence-index.md",
        "docs/fact-ledger.md",
        "docs/algorithm-contract-nsqd.md",
        "docs/ablations/alg-operators.md",
        "docs/ablations/alg-status-window.md",
    ):
        current_text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert OUTPUT_NAME in current_text
        assert "nsqd-operator-f-readiness-2026-09-12-implementation-binding" in current_text
        assert "nsqd-operator-activation-2026-09-12-pointer-sync" in current_text


def test_activation_overlay_keeps_immutable_g_predecessor_binding() -> None:
    overlay_path = REPO_ROOT / (
        "docs/reviews/nsqd-operator-activation-2026-09-11-remediation/activation-status.yaml"
    )
    overlay = overlay_path.read_text(encoding="utf-8")

    assert IMMUTABLE_ACTIVATION_G_BINDING in overlay
    assert PREDECESSOR_NAME not in overlay
    assert OUTPUT_NAME not in overlay
