from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nsqd.domain.operator_g_census import StructuredValue
from nsqd.domain.operator_g_readiness import project_zero_readiness, readiness_source_bindings
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from tests.nsqd.operator_g_census_support import census_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = (
    REPO_ROOT / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review-correction"
)
PREDECESSOR_ROOT = REPO_ROOT / "docs/reviews/nsqd-operator-g-readiness-census-2026-09-09-c-review"
PREDECESSOR_MANIFEST = (
    "../nsqd-operator-g-readiness-census-2026-09-09-c-review/packet-manifest.json"
)
PREDECESSOR_DIGEST = "3a9070604f9e622bc3d2d56f666cc762ae31d85d7bad85c06e531e056c1efc87"
SUCCESSOR_DIGEST = "2509690fecb8800bd99dcb726d31504876c6de37a1c66c5ced33562dcc1439e6"
READINESS_SHA256 = "b57f0146f7620f1d259d90e29efe413b3edde85d789bf4905c22aa994305dfbe"
SNAPSHOT_DIGEST = "9529d91e202fac4043b0faebec22d0460b284dfaf0168d042c5b30007c2c5405"


def _mapping(value: StructuredValue) -> dict[str, StructuredValue]:
    assert isinstance(value, dict)
    return value


def _json(path: Path) -> dict[str, StructuredValue]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")))


def test_c_review_correction_is_stale_but_live_census_remains_complete_zero() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())
    projection = project_zero_readiness(census, readiness_source_bindings(REPO_ROOT))

    assert packet != projection
    assert census.issues == ()
    packet_census = _mapping(packet["census"])
    historical_scope_file_count = packet_census["scope_file_count"]
    assert isinstance(historical_scope_file_count, int)
    assert historical_scope_file_count == 294
    assert packet_census["scope_snapshot_digest"] == SNAPSHOT_DIGEST
    assert census.scope_file_count > historical_scope_file_count
    assert census.scope_snapshot_digest != SNAPSHOT_DIGEST
    assert census.trusted_approval_count == 0
    assert census.trusted_evidence_artifact_count == 0
    assert census.qualifying_record_digests == ()
    assert packet["records"] == []
    assert packet["authority"] == {
        "packet_inclusion_authorized": False,
        "operator_g_eligibility_implied": False,
        "restart_authorized": False,
        "resurrection_authorized": False,
        "runtime_authorized": False,
    }


def test_c_review_correction_preserves_rejected_packet_as_predecessor() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    predecessor_manifest = _json(PREDECESSOR_ROOT / "packet-manifest.json")

    assert packet["predecessor"] == {
        "manifest": PREDECESSOR_MANIFEST,
        "packet_digest": PREDECESSOR_DIGEST,
    }
    assert predecessor_manifest["packet_digest"] == PREDECESSOR_DIGEST
    assert hashlib.sha256((PREDECESSOR_ROOT / "readiness.json").read_bytes()).hexdigest() == (
        "6f029cd618f600b944456647f450a5ed79c0863c32ae27dd6d36f6d100ffda01"
    )
    assert (
        hashlib.sha256((PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()).hexdigest()
        == "530ef21ff55876ee717658487822f1ce988c957755774d6af5456a3b0e81abf4"
    )


def test_c_review_correction_binds_final_c_review_sources() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    source_bindings = packet["source_bindings"]
    assert isinstance(source_bindings, list)
    bindings = {value["path"]: value for value in source_bindings if isinstance(value, dict)}

    assert (
        bindings[
            "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-09/packet-manifest.json"
        ]["sha256"]
        == "baf5ab583e294c4eebee2fcaa2cc73c5e4a985cfd74005af7cf21a39e4aa0abf"
    )
    assert (
        bindings["docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-09/review-summary.json"][
            "sha256"
        ]
        == "643fc415cc2f6b266a7a8bf4c04fdf11e34ede3947dd3be090ad241d3a5f04d4"
    )
    assert (
        bindings["docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-09/review-seal.json"][
            "sha256"
        ]
        == "43119d95b784fa587ae640815b8b71f6c96ccbc6f12d72ab1875edaff39971f2"
    )


def test_c_review_correction_manifest_replays() -> None:
    manifest = _json(PACKET_ROOT / "packet-manifest.json")
    readiness_digest = hashlib.sha256((PACKET_ROOT / "readiness.json").read_bytes()).hexdigest()
    artifacts = {"readiness.json": readiness_digest}
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()

    assert readiness_digest == READINESS_SHA256
    assert manifest == {
        "artifact_sha256": artifacts,
        "packet_digest": hashlib.sha256(preimage).hexdigest(),
        "schema_version": 1,
    }
    assert manifest["packet_digest"] == SUCCESSOR_DIGEST
