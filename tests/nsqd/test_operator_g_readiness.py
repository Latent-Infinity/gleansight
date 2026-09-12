from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from nsqd.domain.operator_g_census import StructuredValue
from nsqd.domain.operator_g_readiness import readiness_source_bindings, sealed_zero_matches
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from tests.nsqd.operator_g_census_support import (
    approved_record,
    census_contract,
    initialize_repository,
    trusted_approval,
    trusted_evidence_artifacts,
    write_evidence,
    write_record,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = (
    REPO_ROOT
    / "docs"
    / "reviews"
    / "nsqd-operator-g-readiness-census-2026-09-09-c-review-correction"
)
CURRENT_PREDECESSOR_ROOT = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-g-readiness-census-2026-09-09-c-review"
)
CORRECTION_PREDECESSOR_ROOT = (
    REPO_ROOT
    / "docs"
    / "reviews"
    / "nsqd-operator-g-readiness-census-2026-09-09-c-cycle-correction"
)
CYCLE_PREDECESSOR_ROOT = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-g-readiness-census-2026-09-09-c-cycle"
)
PROTOCOL_PREDECESSOR_ROOT = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-g-readiness-census-2026-09-09-protocol"
)
CENSUS_PREDECESSOR_ROOT = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-g-readiness-census-2026-09-08"
)
ORIGINAL_PREDECESSOR_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-g-readiness-2026-09-08"
ORIGINAL_PREDECESSOR_DIGEST = "d1e6ef13c8d8f366228a02f92e1848854e9e9d20baff6ff2fb81842e28561be0"
CENSUS_PREDECESSOR_DIGEST = "96e13bb1c2a183b4e797ea1309f0b2f0d4659a05778d0151a4045b44e23c4ee2"
PROTOCOL_PREDECESSOR_DIGEST = "47fa35d858a186a9b1c416cfe7c1003d177aa2c91d72ebd7c5e20d80810efcb8"
CYCLE_PREDECESSOR_DIGEST = "d984bab7ad819fdfd45031d840900b9f0bb74241ae319f5473fe4bb5d3272bad"
CORRECTION_PREDECESSOR_DIGEST = "18808bc2186244f432fd7742dfbaba18c11d1eefcd0e7d90e31b972a501e5844"
CURRENT_PREDECESSOR_DIGEST = "3a9070604f9e622bc3d2d56f666cc762ae31d85d7bad85c06e531e056c1efc87"
SUCCESSOR_DIGEST = "2509690fecb8800bd99dcb726d31504876c6de37a1c66c5ced33562dcc1439e6"


def _mapping(value: StructuredValue) -> dict[str, StructuredValue]:
    assert isinstance(value, dict)
    return value


def _json(path: Path) -> dict[str, StructuredValue]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")))


def _manifest_matches(packet_root: Path) -> bool:
    manifest = _json(packet_root / "packet-manifest.json")
    artifacts = _mapping(manifest["artifact_sha256"])
    readiness_digest = hashlib.sha256((packet_root / "readiness.json").read_bytes()).hexdigest()
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    return (
        artifacts == {"readiness.json": readiness_digest}
        and manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest()
    )


def test_historical_successor_is_stale_after_contract_enforcement_changes() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())

    assert sealed_zero_matches(census, packet, readiness_source_bindings(REPO_ROOT)) is False
    assert packet["packet_kind"] == "operator_g_readiness_census"
    assert packet["evidence_sufficient"] is False
    assert packet["records"] == []
    predecessor = _mapping(packet["predecessor"])
    assert predecessor["packet_digest"] == CURRENT_PREDECESSOR_DIGEST


def test_successor_manifest_replays_deterministically() -> None:
    manifest = _json(PACKET_ROOT / "packet-manifest.json")
    artifacts = _mapping(manifest["artifact_sha256"])
    readiness_digest = hashlib.sha256((PACKET_ROOT / "readiness.json").read_bytes()).hexdigest()

    assert artifacts == {"readiness.json": readiness_digest}
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest()
    assert manifest["packet_digest"] == SUCCESSOR_DIGEST
    assert _manifest_matches(PACKET_ROOT)


def test_stale_manifest_rejects_changed_readiness(tmp_path: Path) -> None:
    shutil.copytree(PACKET_ROOT, tmp_path / "packet")
    packet_root = tmp_path / "packet"
    readiness = _json(packet_root / "readiness.json")
    readiness["qualifying_approved_record_count"] = 1
    (packet_root / "readiness.json").write_text(json.dumps(readiness), encoding="utf-8")

    assert _manifest_matches(packet_root) is False


def test_historical_packets_are_preserved_byte_for_byte() -> None:
    original_manifest = _json(ORIGINAL_PREDECESSOR_ROOT / "packet-manifest.json")
    census_manifest = _json(CENSUS_PREDECESSOR_ROOT / "packet-manifest.json")
    protocol_manifest = _json(PROTOCOL_PREDECESSOR_ROOT / "packet-manifest.json")
    cycle_manifest = _json(CYCLE_PREDECESSOR_ROOT / "packet-manifest.json")
    correction_manifest = _json(CORRECTION_PREDECESSOR_ROOT / "packet-manifest.json")
    current_manifest = _json(CURRENT_PREDECESSOR_ROOT / "packet-manifest.json")

    assert original_manifest["packet_digest"] == ORIGINAL_PREDECESSOR_DIGEST
    assert census_manifest["packet_digest"] == CENSUS_PREDECESSOR_DIGEST
    assert protocol_manifest["packet_digest"] == PROTOCOL_PREDECESSOR_DIGEST
    assert cycle_manifest["packet_digest"] == CYCLE_PREDECESSOR_DIGEST
    assert correction_manifest["packet_digest"] == CORRECTION_PREDECESSOR_DIGEST
    assert current_manifest["packet_digest"] == CURRENT_PREDECESSOR_DIGEST
    assert hashlib.sha256(
        (ORIGINAL_PREDECESSOR_ROOT / "readiness.json").read_bytes()
    ).hexdigest() == ("92f8ad6441df49b77e85abb7cbb88808ceda50e98e3d347ad496b80065ab1903")
    assert hashlib.sha256(
        (ORIGINAL_PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()
    ).hexdigest() == ("333d308c48b6d63c27efcc6b0702294c63f97b099fd7ff4e01446c73e72212d4")
    assert hashlib.sha256(
        (CENSUS_PREDECESSOR_ROOT / "readiness.json").read_bytes()
    ).hexdigest() == ("ee12c356fea8240edf91a21fc8fc296c2872c4d586029cb69c98a95f6ab271f5")
    assert hashlib.sha256(
        (CENSUS_PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()
    ).hexdigest() == ("b4e8a4a0db99693a3ce70b94578a08f3a23e336aadb3150c8cd99c243db36a03")
    assert hashlib.sha256(
        (PROTOCOL_PREDECESSOR_ROOT / "readiness.json").read_bytes()
    ).hexdigest() == ("c3ae294c22b15aa40d0e5a6d58991cec48fae0f9a9d7470d853b7835496cb8fb")
    assert hashlib.sha256(
        (PROTOCOL_PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()
    ).hexdigest() == ("f33b4864b1701006ded4f478a1ff85b27fc16419a9b1d07387d2c0ccd8c547c9")
    assert hashlib.sha256((CYCLE_PREDECESSOR_ROOT / "readiness.json").read_bytes()).hexdigest() == (
        "e7c60bb7032989d819d6ea9e3bf07f9bee880c13307ddc7b243014b10370a942"
    )
    assert hashlib.sha256(
        (CYCLE_PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()
    ).hexdigest() == ("3425998ccb397f26baacb93d3126a278e90cafc458c6d2e984bf009c5dc68bcd")
    assert hashlib.sha256(
        (CORRECTION_PREDECESSOR_ROOT / "readiness.json").read_bytes()
    ).hexdigest() == ("94d77dbfeacfba1370d17c018f59b12d9a657e3dd054615a094aae2da566b4b9")
    assert hashlib.sha256(
        (CORRECTION_PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()
    ).hexdigest() == ("d31a8cdd1715027b7b9df79fec6d773d57934d4152ad781472c283ad8e36aa9f")
    assert hashlib.sha256(
        (CURRENT_PREDECESSOR_ROOT / "readiness.json").read_bytes()
    ).hexdigest() == ("6f029cd618f600b944456647f450a5ed79c0863c32ae27dd6d36f6d100ffda01")
    assert hashlib.sha256(
        (CURRENT_PREDECESSOR_ROOT / "packet-manifest.json").read_bytes()
    ).hexdigest() == ("530ef21ff55876ee717658487822f1ce988c957755774d6af5456a3b0e81abf4")


def test_qualifying_record_elsewhere_in_declared_scope_invalidates_zero_packet(
    tmp_path: Path,
) -> None:
    initialize_repository(tmp_path)
    evidence_digest = write_evidence(tmp_path)
    record = approved_record(evidence_digest)
    write_record(tmp_path, record, "qualifying-g-record.json")

    census = census_operator_g_evidence(
        tmp_path,
        contract=census_contract(),
        trusted_approvals=frozenset({trusted_approval(record)}),
        trusted_evidence_artifacts=trusted_evidence_artifacts(evidence_digest),
    )

    assert len(census.qualifying_record_digests) == 1
    assert (
        sealed_zero_matches(
            census,
            _json(PACKET_ROOT / "readiness.json"),
            readiness_source_bindings(REPO_ROOT),
        )
        is False
    )
    assert census.candidates[0].qualifying is True
    assert record["operator_g_eligible"] is False
    assert record["authorization_state"] == "report_only"


def test_stale_scope_snapshot_invalidates_zero_packet() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    census_data = _mapping(packet["census"])
    census_data["scope_snapshot_digest"] = "0" * 64
    packet["census"] = census_data
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())

    assert sealed_zero_matches(census, packet, readiness_source_bindings(REPO_ROOT)) is False


def test_source_bindings_replay_and_exclude_agent_state() -> None:
    packet = _json(PACKET_ROOT / "readiness.json")
    bindings = packet["source_bindings"]
    assert isinstance(bindings, list)
    for value in bindings:
        binding = _mapping(value)
        path = binding["path"]
        digest = binding["sha256"]
        assert isinstance(path, str)
        assert isinstance(digest, str)
        assert ".omo" not in Path(path).parts
        assert len(digest) == 64

    assert packet["source_bindings"] != [
        {"path": binding.path, "role": binding.role, "sha256": binding.sha256}
        for binding in readiness_source_bindings(REPO_ROOT)
    ]


def test_live_source_bindings_include_every_split_contract_module() -> None:
    bindings = {binding.role: binding.path for binding in readiness_source_bindings(REPO_ROOT)}

    assert bindings["external_approval_boundary"] == "src/nsqd/domain/operator_approval.py"
    assert bindings["typed_approval_errors"] == "src/nsqd/domain/operator_approval_errors.py"
    assert bindings["shared_contract_validation"] == "src/nsqd/domain/contract_validation.py"
    assert bindings["typed_contract_validation_errors"] == (
        "src/nsqd/domain/contract_validation_errors.py"
    )
    assert bindings["canonical_failure_record_facade"] == "src/nsqd/domain/operator_g.py"
    assert bindings["census_domain_types"] == "src/nsqd/domain/operator_g_census_types.py"
    assert bindings["canonical_failure_record_validation"] == (
        "src/nsqd/domain/operator_g_record_validation.py"
    )
    assert bindings["release_failure_record_validation"] == (
        "src/nsqd/domain/operator_g_release_validation.py"
    )
    assert bindings["failure_record_contract_types"] == "src/nsqd/domain/operator_g_types.py"
    assert bindings["typed_structured_input_boundary"] == (
        "src/nsqd/infrastructure/operator_g_structured_inputs.py"
    )
