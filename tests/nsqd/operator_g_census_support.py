from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import yaml

from nsqd.domain.operator_approval import OperatorApprovalKind, TrustedOperatorApproval
from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    operator_g_registration_digest,
)
from nsqd.domain.operator_g_census import StructuredValue
from nsqd.domain.operator_g_evidence import (
    OperatorGEvidenceRole,
    TrustedOperatorGEvidenceArtifact,
)
from nsqd.infrastructure.operator_g_census_files import APPROVED_INPUT_ROOT
from nsqd.infrastructure.operator_g_census_formats import normalize
from tests.nsqd.operator_dg_contract_support import operator_g_record

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V2_CONTRACT_PATH = (
    REPOSITORY_ROOT / "evidence/contracts/nsqd/operator-g/v2/failure-record-contract-v2.yaml"
)


def registered_record() -> dict[str, StructuredValue]:
    loaded = normalize(json.loads(json.dumps(operator_g_record())))
    assert isinstance(loaded, dict)
    record = loaded
    record.update(
        {
            "schema_version": 2,
            "scientific_purpose": "Test whether the registered method beats the fixed baseline.",
            "registered_at_utc": "2026-09-05T17:00:00Z",
            "registration_digest": "0" * 64,
            "exact_command": "uv run python -m nsqd.experiment --id experiment-001",
            "resource_cap": {
                "wall_clock_seconds": 3600,
                "memory_bytes": 1073741824,
                "cpu_cores": 2,
            },
            "predeclared_success_failure_and_inconclusive_outcomes": {
                "success": "validation_loss < 1.0",
                "failure": "validation_loss >= 1.0",
                "inconclusive": "measurement evidence is incomplete",
            },
            "exit_status": 1,
            "measured_outcome": {"validation_loss": 1.2, "baseline_loss": 1.0},
            "failure_classification": "method",
            "cleanup_receipt": "9" * 64,
        }
    )
    triggers = sequence(record["changed_condition_triggers"])
    trigger = mapping(triggers[0])
    trigger.update(
        {
            "measured_variable": "data_regime",
            "comparison_rule": "candidate differs from registered original",
        }
    )
    record["changed_condition_triggers"] = [trigger]
    restarts = sequence(record["restart_conditions"])
    restart = mapping(restarts[0])
    restart.update(
        {
            "required_evidence_digest": "f" * 64,
            "decision_owner": "human:restart-owner",
        }
    )
    record["restart_conditions"] = [restart]
    record["provenance"] = {
        "generated_by": "agent:g-recorder",
        "producer_session": "session:g-producer",
    }
    review = mapping(record["review"])
    review.update({"reviewer_session": None, "approval_scope": None})
    record["review"] = review
    record["registration_digest"] = operator_g_registration_digest(record)
    return record


def initialize_repository(root: Path) -> None:
    (root / APPROVED_INPUT_ROOT).mkdir(parents=True)
    for legacy_root in ("docs", "src", "tests"):
        (root / legacy_root).mkdir()


def write_evidence(
    root: Path, content: bytes = b"{}\n", *, input_root: str = APPROVED_INPUT_ROOT
) -> str:
    digest = hashlib.sha256(content).hexdigest()
    (root / input_root / "evidence.json").write_bytes(content)
    return digest


def census_contract() -> dict[str, StructuredValue]:
    contract = normalize(yaml.safe_load(V2_CONTRACT_PATH.read_text(encoding="utf-8")))
    assert isinstance(contract, dict)
    return contract


def approved_record(
    evidence_digest: str, record_id: str = "G-FAIL-001"
) -> dict[str, StructuredValue]:
    record = registered_record()
    record["failure_record_id"] = record_id
    record["immutable_source_artifact_digests"] = [evidence_digest]
    record["cleanup_receipt"] = evidence_digest
    outcome = mapping(record["outcome"])
    outcome["evidence_artifact_digests"] = [evidence_digest]
    record["outcome"] = outcome
    triggers = sequence(record["changed_condition_triggers"])
    trigger = mapping(triggers[0])
    trigger["evidence_artifact_digests"] = [evidence_digest]
    record["changed_condition_triggers"] = [trigger]
    restarts = sequence(record["restart_conditions"])
    restart = mapping(restarts[0])
    restart["required_evidence_digest"] = evidence_digest
    record["restart_conditions"] = [restart]
    record["registration_digest"] = operator_g_registration_digest(record)
    record["review"] = {
        "review_status": "approved",
        "human_reviewer": "human:independent-reviewer",
        "reviewer_session": "session:g-reviewer",
        "human_approved_at_utc": "2026-09-08T12:00:00Z",
        "approval_scope": "operator_g_record_admission",
        "approved_record_digest": None,
    }
    digest = operator_g_failure_record_digest(record)
    review = mapping(record["review"])
    review["approved_record_digest"] = digest
    record["review"] = review
    return record


def trusted_approval(record: Mapping[str, StructuredValue]) -> TrustedOperatorApproval:
    review = mapping(record["review"])
    digest = review["approved_record_digest"]
    reviewer = review["human_reviewer"]
    approved_at = review["human_approved_at_utc"]
    assert isinstance(digest, str)
    assert isinstance(reviewer, str)
    assert isinstance(approved_at, str)
    return TrustedOperatorApproval(
        OperatorApprovalKind.G_FAILURE_RECORD,
        digest,
        reviewer,
        datetime.fromisoformat(approved_at.replace("Z", "+00:00")).astimezone(UTC),
        reviewer_session="session:g-reviewer",
        approval_scope="operator_g_record_admission",
    )


def trusted_evidence_artifacts(
    digest: str,
    *,
    path: str = f"{APPROVED_INPUT_ROOT}/evidence.json",
    roles: tuple[OperatorGEvidenceRole, ...] = tuple(OperatorGEvidenceRole),
) -> frozenset[TrustedOperatorGEvidenceArtifact]:
    return frozenset(TrustedOperatorGEvidenceArtifact(role, path, digest) for role in roles)


def write_record(
    root: Path,
    record: Mapping[str, StructuredValue],
    name: str = "record.json",
    *,
    input_root: str = APPROVED_INPUT_ROOT,
) -> Path:
    path = root / input_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return path


def mapping(value: StructuredValue) -> dict[str, StructuredValue]:
    assert isinstance(value, dict)
    return value


def sequence(value: StructuredValue) -> list[StructuredValue]:
    assert isinstance(value, list)
    return list(value)
