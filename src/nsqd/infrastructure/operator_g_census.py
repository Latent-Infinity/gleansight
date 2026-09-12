from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from nsqd.domain.operator_approval import TrustedOperatorApproval
from nsqd.domain.operator_g_census import (
    CandidateClass,
    CandidateEvidence,
    CensusConfiguration,
    CensusIssue,
    CensusStatus,
    OperatorGCensus,
    ReasonCode,
    RecordLocator,
    build_inventory,
    classify_failure_record,
    resolve_candidates,
)
from nsqd.domain.operator_g_evidence import TrustedOperatorGEvidenceArtifact
from nsqd.domain.operator_g_types import StructuredValue
from nsqd.infrastructure.operator_g_census_files import (
    DEFAULT_LIMITS,
    ROOTS,
    STRUCTURED_SUFFIXES,
    CensusLimits,
    ScannedFile,
    discover,
    read_trusted_evidence_paths,
)
from nsqd.infrastructure.operator_g_census_formats import (
    CalibrationFile,
    StructuredFormatError,
    derive_calibrations,
    parse_documents,
    record_candidates,
)

ALGORITHM_VERSION: Final = "operator-g-evidence-census/v4"
SYNTHETIC_FIXTURE: Final = "tests/nsqd/operator_dg_contract_support.py"


def census_operator_g_evidence(
    repository_root: Path,
    *,
    contract: Mapping[str, StructuredValue],
    trusted_approvals: frozenset[TrustedOperatorApproval] = frozenset(),
    trusted_evidence_artifacts: frozenset[TrustedOperatorGEvidenceArtifact] = frozenset(),
    limits: CensusLimits = DEFAULT_LIMITS,
) -> OperatorGCensus:
    configuration = CensusConfiguration(
        ROOTS,
        tuple(sorted(STRUCTURED_SUFFIXES)),
        limits.max_files,
        limits.max_file_bytes,
        limits.max_total_bytes,
        limits.max_depth,
        limits.max_structured_depth,
    )
    files, issues = discover(repository_root, limits)
    available_paths_by_digest = read_trusted_evidence_paths(
        repository_root,
        (artifact.path for artifact in trusted_evidence_artifacts),
        limits,
    )
    candidates: list[CandidateEvidence] = []
    for file in files:
        candidates.extend(
            _classify_file(
                file,
                contract,
                trusted_approvals,
                trusted_evidence_artifacts,
                available_paths_by_digest,
                issues,
                limits.max_structured_depth,
            )
        )
    candidates.extend(_calibration_inventory(files, issues, limits.max_structured_depth))
    candidates = resolve_candidates(candidates)
    blocking_reasons = {
        ReasonCode.CONFLICTING_ID,
        ReasonCode.FORBIDDEN_SOURCE,
        ReasonCode.MALFORMED,
        ReasonCode.MISSING_EVIDENCE,
        ReasonCode.UNTRUSTED,
    }
    issues.extend(
        CensusIssue(str(item.locator), item.reason_code.value)
        for item in candidates
        if item.reason_code in blocking_reasons
    )
    status = CensusStatus.COMPLETE if not issues else CensusStatus.INCOMPLETE
    inventory = build_inventory(candidates)
    qualifying = (
        tuple(
            sorted(
                {
                    item.canonical_digest
                    for item in candidates
                    if item.qualifying and item.canonical_digest
                }
            )
        )
        if status is CensusStatus.COMPLETE
        else ()
    )
    snapshot_preimage = {
        "algorithm_version": ALGORITHM_VERSION,
        "configuration": {
            "roots": configuration.roots,
            "structured_suffixes": configuration.structured_suffixes,
            "max_files": configuration.max_files,
            "max_file_bytes": configuration.max_file_bytes,
            "max_total_bytes": configuration.max_total_bytes,
            "max_depth": configuration.max_depth,
            "max_structured_depth": configuration.max_structured_depth,
        },
        "files": [{"path": file.path, "sha256": file.sha256} for file in files],
    }
    snapshot = hashlib.sha256(
        json.dumps(snapshot_preimage, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return OperatorGCensus(
        ALGORITHM_VERSION,
        configuration,
        status,
        snapshot,
        len(files),
        len(trusted_approvals),
        len(trusted_evidence_artifacts),
        tuple(candidates),
        inventory,
        qualifying,
        tuple(sorted(issues, key=lambda issue: (issue.path, issue.reason))),
    )


def _classify_file(
    file: ScannedFile,
    contract: Mapping[str, StructuredValue],
    trusted: frozenset[TrustedOperatorApproval],
    trusted_evidence: frozenset[TrustedOperatorGEvidenceArtifact],
    available_paths_by_digest: Mapping[str, frozenset[str]],
    issues: list[CensusIssue],
    max_structured_depth: int,
) -> list[CandidateEvidence]:
    if file.path == SYNTHETIC_FIXTURE:
        return _synthetic_fixture(file, issues)
    try:
        documents = parse_documents(file.path, file.content, max_structured_depth)
    except StructuredFormatError:
        issues.append(CensusIssue(file.path, "malformed_structured_file"))
        return [
            CandidateEvidence(
                RecordLocator(f"{file.path}#malformed"),
                CandidateClass.MALFORMED,
                ReasonCode.MALFORMED,
            )
        ]
    candidates: list[CandidateEvidence] = []
    for document_index, document in enumerate(documents):
        for locator, record in record_candidates(document, f"{file.path}#{document_index}"):
            candidates.append(
                classify_failure_record(
                    record,
                    locator=RecordLocator(locator),
                    contract=contract,
                    trusted_approvals=trusted,
                    trusted_evidence_artifacts=trusted_evidence,
                    available_paths_by_digest=available_paths_by_digest,
                )
            )
    return candidates


def _synthetic_fixture(file: ScannedFile, issues: list[CensusIssue]) -> list[CandidateEvidence]:
    try:
        tree = ast.parse(file.content, filename=file.path)
    except SyntaxError:
        issues.append(CensusIssue(file.path, "malformed_synthetic_fixture"))
        return []
    count = sum(
        isinstance(node, ast.FunctionDef) and node.name == "operator_g_record" for node in tree.body
    )
    return _simple_candidates(
        file.path, count, CandidateClass.SYNTHETIC_FIXTURE, ReasonCode.SYNTHETIC_PENDING
    )


def _calibration_inventory(
    files: list[ScannedFile], issues: list[CensusIssue], max_structured_depth: int
) -> list[CandidateEvidence]:
    results = derive_calibrations(
        [CalibrationFile(file.path, file.content, file.sha256) for file in files],
        max_structured_depth,
    )
    candidates: list[CandidateEvidence] = []
    for result in results:
        if not result.reconciled:
            issues.append(CensusIssue(result.root, "candidate_hash_reconciliation_failed"))
        candidates.extend(
            _simple_candidates(
                result.measurement_path,
                result.measurement_count,
                CandidateClass.TAU_MEASUREMENT,
                ReasonCode.TAU_NOT_EXPERIMENT,
            )
        )
        candidates.extend(
            _simple_candidates(
                result.study_path,
                result.study_count,
                CandidateClass.UNEXECUTED_STUDY,
                ReasonCode.UNEXECUTED,
            )
        )
    return candidates


def _simple_candidates(
    path: str, count: int, candidate_class: CandidateClass, reason: ReasonCode
) -> list[CandidateEvidence]:
    return [
        CandidateEvidence(RecordLocator(f"{path}#{index}"), candidate_class, reason)
        for index in range(count)
    ]
