from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final

FORBIDDEN_EVIDENCE_SOURCES: Final = frozenset(
    {
        "test_failure_without_experiment_evidence",
        "job_error_code",
        "sufficiency_failure",
        "inferred_or_invented_failure",
        "absence_of_published_or_successful_results",
    }
)


class OperatorGEvidenceRole(StrEnum):
    IMMUTABLE_SOURCE_ARTIFACT = "immutable_source_artifact"
    MEASURED_OUTCOME_EVIDENCE = "measured_outcome_evidence"
    CHANGED_CONDITION_TRIGGER_EVIDENCE = "changed_condition_trigger_evidence"
    RESTART_CONDITION_EVIDENCE = "restart_condition_evidence"
    CLEANUP_RECEIPT = "cleanup_receipt"


@dataclass(frozen=True, slots=True)
class TrustedEvidenceArtifactError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class TrustedOperatorGEvidenceArtifact:
    role: OperatorGEvidenceRole
    path: str
    sha256: str

    def __post_init__(self) -> None:
        relative = PurePosixPath(self.path)
        if type(self.role) is not OperatorGEvidenceRole:
            raise TrustedEvidenceArtifactError("evidence role is invalid")
        if (
            not self.path
            or self.path != self.path.strip()
            or "\\" in self.path
            or relative.is_absolute()
            or relative.as_posix() != self.path
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise TrustedEvidenceArtifactError(
                "evidence path must be an exact nonblank repository-relative path"
            )
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise TrustedEvidenceArtifactError(
                "evidence sha256 must be a lowercase SHA-256 hex digest"
            )
