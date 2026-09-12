from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Final

import yaml

import nsqd.domain.operator_f_pilot as operator_f

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PACKET_ROOT: Final = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
PROJECTION_ROOT: Final = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-projection-review-2026-08-28" / "final"
)
JEPA_ROOT: Final = REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
POLICY_PATH: Final = (
    REPO_ROOT / "tests" / "fixtures" / "approved" / "nsqd" / "policies" / "finance-1.toml"
)
RESULT_PATH: Final = PACKET_ROOT / "operator-f-validation-target-pilot.json"
SHUFFLE_SEED: Final = "operator-f/F-PROP-001/validation_target/control-v1"
SNAPSHOT_ID: Final = "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
PROPOSAL_DIGEST: Final = "a" * 64
HISTORICAL_RESULT_SHA256: Final = "888d1e7c9d3fab43713b76dad3c66749466d00ac5313a0e8de87b3f4b542252a"
HISTORICAL_RESULT_DIGEST: Final = "9523f57d449fa2abbf6e5525ba13477f2ec8d79fbcd481aed1f73850898f8fb3"


def _records() -> tuple[operator_f.OperatorFPilotRecord, ...]:
    coordinates = operator_f.RegisteredAxisCoordinates
    record = operator_f.OperatorFPilotRecord
    return (
        record(
            record_id="N11-FIN-01",
            projection_sha256="1" * 64,
            registered_coordinates=None,
            validation_target="representation_fidelity",
        ),
        record(
            record_id="N11-FIN-02",
            projection_sha256="2" * 64,
            registered_coordinates=coordinates(
                mechanism="shock-propagation",
                target="signal-decay",
                horizon="event-time",
            ),
            validation_target="predictive_task",
        ),
        record(
            record_id="N11-FIN-03",
            projection_sha256="3" * 64,
            registered_coordinates=coordinates(
                mechanism="flow-driven",
                target="returns",
                horizon="intraday",
            ),
            validation_target="economic_utility",
        ),
        record(
            record_id="N11-FIN-04",
            projection_sha256="4" * 64,
            registered_coordinates=coordinates(
                mechanism="flow-driven",
                target="returns",
                horizon="daily",
            ),
            validation_target="economic_utility",
        ),
        record(
            record_id="N11-FIN-05",
            projection_sha256="5" * 64,
            registered_coordinates=None,
            validation_target="predictive_task",
        ),
    )


def _inputs(
    records: tuple[operator_f.OperatorFPilotRecord, ...] | None = None,
) -> operator_f.OperatorFPilotInputs:
    return operator_f.OperatorFPilotInputs(
        proposal_id="F-PROP-001",
        approved_proposal_digest=PROPOSAL_DIGEST,
        source_snapshot_id=SNAPSHOT_ID,
        source_artifacts=(
            operator_f.OperatorFSourceArtifact(path="proposal.yaml", sha256="a" * 64),
            operator_f.OperatorFSourceArtifact(path="results.json", sha256="b" * 64),
            *tuple(
                operator_f.OperatorFSourceArtifact(
                    path=f"N11-FIN-0{index}.yaml", sha256=str(index) * 64
                )
                for index in range(1, 7)
            ),
        ),
        records=_records() if records is None else records,
        shuffle_seed=SHUFFLE_SEED,
    )


_PINNED_SOURCE_HASHES: Final = {
    (
        "docs/reviews/nsqd-operator-activation-2026-08-30/axis-candidate-contract.yaml"
    ): "50655378e33aee1dc653458464aa020eef6ec098feb9981a146afe29fd150346",
    (
        "docs/reviews/nsqd-operator-activation-2026-08-30/"
        "axis-candidate-proposal-validation-target.yaml"
    ): "0849bd0c6231279d767fda0c4e850de1854f303ce496ee136e06f3e7df310fd5",
    (
        "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/results.json"
    ): "cdcb6eb1c274c17cbb71c5a76cf8c439d0bc021b2149225b4b27b550360705f2",
    (
        "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/source-ledger.json"
    ): "12889d817f4a6e13e2187c7d28bd0059c1a2c08d0a33b453012dc8b2cbf451ae",
    (
        "docs/reviews/nsqd-projection-review-2026-08-28/final/manifest.toml"
    ): "4c2e3c007969c0081cd2ef254bd6c674aed872cd2edc863247370219b51ba638",
    (
        "tests/fixtures/approved/nsqd/policies/finance-1.toml"
    ): "38f81d80e2858bb1a26a55ad51af24295e9dd4de215c4dbf32cfc098749787f5",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def historical_operator_f_inputs() -> operator_f.OperatorFPilotInputs:
    """Build trusted pilot inputs from independently pinned approved sources."""
    for relative_path, expected_hash in _PINNED_SOURCE_HASHES.items():
        assert _sha256(REPO_ROOT / relative_path) == expected_hash

    proposal = _load_yaml(PACKET_ROOT / "axis-candidate-proposal-validation-target.yaml")
    manifest = tomllib.loads((PROJECTION_ROOT / "manifest.toml").read_text(encoding="utf-8"))
    results = _load_json(JEPA_ROOT / "results.json")
    ledger = _load_json(JEPA_ROOT / "source-ledger.json")
    policy = tomllib.loads(POLICY_PATH.read_text(encoding="utf-8"))
    labels = results["candidate_axis_hypothesis"]["observed_values"]
    manifest_rows = manifest["fixture"]
    ledger_rows = {row["record_id"]: row for row in ledger["records"]}
    records: list[operator_f.OperatorFPilotRecord] = []

    for index in range(1, 6):
        record_id = f"N11-FIN-0{index}"
        projection_path = PROJECTION_ROOT / f"{record_id}.yaml"
        projection = _load_yaml(projection_path)
        manifest_row = manifest_rows[record_id]
        ledger_row = ledger_rows[record_id]
        projection_hash = _sha256(projection_path)
        excerpt_path = PROJECTION_ROOT / projection["source_excerpt_path"]
        assert projection["id"] == manifest_row["id"]
        assert manifest_row["id"] == ledger_row["record_id"] == record_id
        assert projection["domain_policy_id"] == manifest_row["domain_policy_id"]
        assert manifest_row["domain_policy_id"] == ledger_row["domain_policy_id"]
        assert ledger_row["domain_policy_id"] == policy["policy_id"]
        assert projection["source_paper_id"] == manifest_row["source_paper_id"]
        assert manifest_row["source_paper_id"] == ledger_row["source_paper_id"]
        assert projection_hash == manifest_row["content_sha256"] == ledger_row["projection_sha256"]
        assert projection["source_excerpt_path"] == manifest_row["excerpt_path"]
        assert manifest_row["excerpt_path"] == ledger_row["approved_excerpt"]
        assert _sha256(excerpt_path) == manifest_row["excerpt_sha256"]
        assert manifest_row["excerpt_sha256"] == ledger_row["approved_excerpt_sha256"]
        coordinates = projection.get("coordinates")
        if coordinates is not None:
            axes = ("mechanism", "target", "horizon")
            assert all(coordinates[axis] in policy["axes"][axis] for axis in axes)
        records.append(
            operator_f.OperatorFPilotRecord(
                record_id=record_id,
                projection_sha256=projection_hash,
                registered_coordinates=coordinates,
                validation_target=labels[record_id],
            )
        )

    proposal_review = proposal["review"]
    assert proposal["proposal_id"] == "F-PROP-001"
    assert proposal_review["status"] == "human_approved"
    assert proposal_review["approval_scope"] == "evaluation_only"
    assert proposal["candidate_axis"]["name"] == results["candidate_axis_hypothesis"]["axis_id"]
    assert proposal["provenance"]["source_artifact_digests"] == [
        _sha256(JEPA_ROOT / "results.json")
    ]
    assert tuple(labels) == tuple(record.record_id for record in records)
    source_paths = tuple(
        path for path in _PINNED_SOURCE_HASHES if not path.endswith("manifest.toml")
    )
    projection_paths = tuple(
        f"docs/reviews/nsqd-projection-review-2026-08-28/final/N11-FIN-0{index}.yaml"
        for index in range(1, 6)
    )
    source_artifacts = tuple(
        operator_f.OperatorFSourceArtifact(path=path, sha256=_sha256(REPO_ROOT / path))
        for path in (*source_paths[:-1], *projection_paths, source_paths[-1:][0])
    )
    return operator_f.OperatorFPilotInputs(
        proposal_id=proposal["proposal_id"],
        approved_proposal_digest=proposal_review["approved_proposal_digest"],
        source_snapshot_id=proposal["source_snapshot_ids"][0],
        source_artifacts=source_artifacts,
        records=tuple(records),
        shuffle_seed=SHUFFLE_SEED,
    )


def canonical_result_digest(payload: dict[str, operator_f.JsonValue]) -> str:
    preimage = dict(payload)
    preimage["result_digest"] = None
    encoded = json.dumps(
        preimage,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
