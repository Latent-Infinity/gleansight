from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NewType

from nsqd.domain.contract_validation_errors import ContractValidationError
from nsqd.domain.operator_approval import TrustedOperatorApproval
from nsqd.domain.operator_approval_errors import ApprovalErrorReason, OperatorApprovalError
from nsqd.domain.operator_g import (
    operator_g_failure_record_digest,
    validate_operator_g_failure_record,
)
from nsqd.domain.operator_g_census_types import (
    CandidateClass as CandidateClass,
)
from nsqd.domain.operator_g_census_types import (
    CensusStatus as CensusStatus,
)
from nsqd.domain.operator_g_census_types import (
    ReasonCode as ReasonCode,
)
from nsqd.domain.operator_g_evidence import (
    FORBIDDEN_EVIDENCE_SOURCES,
    OperatorGEvidenceRole,
    TrustedOperatorGEvidenceArtifact,
)
from nsqd.domain.operator_g_types import StructuredValue

RecordDigest = NewType("RecordDigest", str)
RecordLocator = NewType("RecordLocator", str)


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    locator: RecordLocator
    candidate_class: CandidateClass
    reason_code: ReasonCode
    failure_record_id: str | None = None
    canonical_digest: RecordDigest | None = None
    qualifying: bool = False


@dataclass(frozen=True, slots=True)
class CensusIssue:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryCount:
    candidate_class: CandidateClass
    observed_count: int
    qualifying_count: int
    reason_code: ReasonCode


@dataclass(frozen=True, slots=True)
class CensusConfiguration:
    roots: tuple[str, ...]
    structured_suffixes: tuple[str, ...]
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    max_depth: int
    max_structured_depth: int


@dataclass(frozen=True, slots=True)
class OperatorGCensus:
    algorithm_version: str
    configuration: CensusConfiguration
    status: CensusStatus
    scope_snapshot_digest: str
    scope_file_count: int
    trusted_approval_count: int
    trusted_evidence_artifact_count: int
    candidates: tuple[CandidateEvidence, ...]
    inventory: tuple[InventoryCount, ...]
    qualifying_record_digests: tuple[RecordDigest, ...]
    issues: tuple[CensusIssue, ...]

    @property
    def substantiates_zero(self) -> bool:
        return self.status is CensusStatus.COMPLETE and not self.qualifying_record_digests


def classify_failure_record(
    record: Mapping[str, StructuredValue],
    *,
    locator: RecordLocator,
    contract: Mapping[str, StructuredValue],
    trusted_approvals: frozenset[TrustedOperatorApproval],
    trusted_evidence_artifacts: frozenset[TrustedOperatorGEvidenceArtifact],
    available_paths_by_digest: Mapping[str, frozenset[str]],
) -> CandidateEvidence:
    failure_record_value = record.get("failure_record_id")
    failure_record_id = failure_record_value if isinstance(failure_record_value, str) else None
    if record.get("template_only") is True:
        return CandidateEvidence(
            locator, CandidateClass.CONTRACT_TEMPLATE, ReasonCode.CONTRACT_TEMPLATE
        )
    if record.get("source_class") in FORBIDDEN_EVIDENCE_SOURCES:
        return CandidateEvidence(
            locator,
            CandidateClass.MALFORMED,
            ReasonCode.FORBIDDEN_SOURCE,
            failure_record_id,
        )
    review = _mapping_or_none(record.get("review"))
    review_status = review.get("review_status") if review is not None else None
    try:
        validated = validate_operator_g_failure_record(
            record,
            contract=contract,
            trusted_approvals=trusted_approvals,
        )
    except OperatorApprovalError as error:
        reason = (
            ReasonCode.UNTRUSTED
            if error.reason is ApprovalErrorReason.MISSING_TRUSTED_APPROVAL
            else ReasonCode.MALFORMED
        )
        return CandidateEvidence(locator, CandidateClass.MALFORMED, reason, failure_record_id)
    except ContractValidationError:
        return CandidateEvidence(
            locator, CandidateClass.MALFORMED, ReasonCode.MALFORMED, failure_record_id
        )
    except ValueError:
        return CandidateEvidence(
            locator, CandidateClass.MALFORMED, ReasonCode.MALFORMED, failure_record_id
        )
    if validated.get("schema_version") != 2 or review_status != "approved":
        return CandidateEvidence(
            locator,
            CandidateClass.PENDING,
            ReasonCode.UNAPPROVED,
            failure_record_id,
        )
    digest = RecordDigest(operator_g_failure_record_digest(validated))
    if not _evidence_is_trusted(validated, trusted_evidence_artifacts, available_paths_by_digest):
        return CandidateEvidence(
            locator,
            CandidateClass.APPROVED_FAILURE_RECORD,
            ReasonCode.MISSING_EVIDENCE,
            failure_record_id,
            digest,
        )
    return CandidateEvidence(
        locator,
        CandidateClass.APPROVED_FAILURE_RECORD,
        ReasonCode.QUALIFYING,
        failure_record_id,
        digest,
        qualifying=True,
    )


def build_inventory(candidates: Sequence[CandidateEvidence]) -> tuple[InventoryCount, ...]:
    counts = Counter((item.candidate_class, item.reason_code) for item in candidates)
    qualified = Counter(
        (item.candidate_class, item.reason_code) for item in candidates if item.qualifying
    )
    for key in (
        (CandidateClass.TEST_FAILURE, ReasonCode.FORBIDDEN_TEST_FAILURE),
        (CandidateClass.JOB_ERROR, ReasonCode.FORBIDDEN_JOB_ERROR),
        (CandidateClass.SUFFICIENCY_FAILURE, ReasonCode.FORBIDDEN_SUFFICIENCY),
    ):
        counts.setdefault(key, 0)
    ordered = sorted(counts.items(), key=lambda item: (item[0][0].value, item[0][1].value))
    return tuple(
        InventoryCount(candidate_class, count, qualified[(candidate_class, reason)], reason)
        for (candidate_class, reason), count in ordered
        if candidate_class is not CandidateClass.CONTRACT_TEMPLATE
    )


def resolve_candidates(candidates: Sequence[CandidateEvidence]) -> list[CandidateEvidence]:
    ordered = sorted(candidates, key=lambda item: str(item.locator))
    digests_by_id: dict[str, set[RecordDigest]] = {}
    for item in ordered:
        if item.failure_record_id and item.canonical_digest:
            digests_by_id.setdefault(item.failure_record_id, set()).add(item.canonical_digest)
    conflicts = {record_id for record_id, digests in digests_by_id.items() if len(digests) > 1}
    seen: set[RecordDigest] = set()
    result: list[CandidateEvidence] = []
    for item in ordered:
        if item.failure_record_id in conflicts:
            result.append(
                CandidateEvidence(
                    item.locator,
                    item.candidate_class,
                    ReasonCode.CONFLICTING_ID,
                    item.failure_record_id,
                    item.canonical_digest,
                )
            )
        elif item.qualifying and item.canonical_digest in seen:
            result.append(
                CandidateEvidence(
                    item.locator,
                    item.candidate_class,
                    ReasonCode.DUPLICATE,
                    item.failure_record_id,
                    item.canonical_digest,
                )
            )
        else:
            result.append(item)
            if item.qualifying and item.canonical_digest:
                seen.add(item.canonical_digest)
    return result


def _evidence_requirements(
    record: Mapping[str, StructuredValue],
) -> frozenset[tuple[OperatorGEvidenceRole, str]]:
    values = {
        (OperatorGEvidenceRole.IMMUTABLE_SOURCE_ARTIFACT, digest)
        for digest in _strings(record.get("immutable_source_artifact_digests"))
    }
    outcome = _mapping_or_none(record.get("outcome"))
    if outcome is not None:
        values.update(
            (OperatorGEvidenceRole.MEASURED_OUTCOME_EVIDENCE, digest)
            for digest in _strings(outcome.get("evidence_artifact_digests"))
        )
    triggers = record.get("changed_condition_triggers")
    if isinstance(triggers, list):
        for trigger in triggers:
            trigger_mapping = _mapping_or_none(trigger)
            if trigger_mapping is not None:
                values.update(
                    (OperatorGEvidenceRole.CHANGED_CONDITION_TRIGGER_EVIDENCE, digest)
                    for digest in _strings(trigger_mapping.get("evidence_artifact_digests"))
                )
    cleanup_receipt = record.get("cleanup_receipt")
    if isinstance(cleanup_receipt, str):
        values.add((OperatorGEvidenceRole.CLEANUP_RECEIPT, cleanup_receipt))
    restarts = record.get("restart_conditions")
    if isinstance(restarts, list):
        for restart in restarts:
            restart_mapping = _mapping_or_none(restart)
            if restart_mapping is not None:
                values.update(
                    (OperatorGEvidenceRole.RESTART_CONDITION_EVIDENCE, digest)
                    for digest in _strings([restart_mapping.get("required_evidence_digest")])
                )
    return frozenset(values)


def _evidence_is_trusted(
    record: Mapping[str, StructuredValue],
    trusted: frozenset[TrustedOperatorGEvidenceArtifact],
    available_paths_by_digest: Mapping[str, frozenset[str]],
) -> bool:
    trusted_keys = {
        (artifact.role, artifact.sha256)
        for artifact in trusted
        if artifact.path in available_paths_by_digest.get(artifact.sha256, frozenset())
    }
    return _evidence_requirements(record).issubset(trusted_keys)


def _strings(value: StructuredValue) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _mapping_or_none(value: StructuredValue) -> dict[str, StructuredValue] | None:
    return value if isinstance(value, dict) else None
