from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nsqd.domain.operator_g_census import OperatorGCensus
from nsqd.domain.operator_g_readiness_projection import CREATED_AT_UTC as CREATED_AT_UTC
from nsqd.domain.operator_g_readiness_projection import PREDECESSOR_DIGEST as PREDECESSOR_DIGEST
from nsqd.domain.operator_g_readiness_projection import (
    PREDECESSOR_MANIFEST as PREDECESSOR_MANIFEST,
)
from nsqd.domain.operator_g_readiness_projection import SourceBinding as SourceBinding
from nsqd.domain.operator_g_readiness_projection import (
    project_zero_readiness as project_zero_readiness,
)
from nsqd.domain.operator_g_types import StructuredValue


@dataclass(frozen=True, slots=True)
class _SourceSpec:
    path: str
    role: str


SOURCE_SPECS: Final = (
    _SourceSpec(
        "evidence/contracts/nsqd/operator-g/v1/failure-record-contract.yaml",
        "canonical_failure_record_contract_v1",
    ),
    _SourceSpec(
        "evidence/contracts/nsqd/operator-g/v2/failure-record-contract-v2.yaml",
        "canonical_failure_record_contract_v2",
    ),
    _SourceSpec("src/nsqd/domain/contract_validation.py", "shared_contract_validation"),
    _SourceSpec(
        "src/nsqd/domain/contract_validation_errors.py", "typed_contract_validation_errors"
    ),
    _SourceSpec("src/nsqd/domain/operator_approval.py", "external_approval_boundary"),
    _SourceSpec("src/nsqd/domain/operator_approval_errors.py", "typed_approval_errors"),
    _SourceSpec("src/nsqd/domain/operator_g.py", "canonical_failure_record_facade"),
    _SourceSpec("src/nsqd/domain/operator_g_census.py", "census_domain_algorithm"),
    _SourceSpec("src/nsqd/domain/operator_g_census_types.py", "census_domain_types"),
    _SourceSpec("src/nsqd/domain/operator_g_evidence.py", "evidence_trust_boundary"),
    _SourceSpec("src/nsqd/domain/operator_g_readiness.py", "readiness_projection_validator"),
    _SourceSpec(
        "src/nsqd/domain/operator_g_readiness_projection.py", "readiness_projection_builder"
    ),
    _SourceSpec(
        "src/nsqd/domain/operator_g_record_validation.py",
        "canonical_failure_record_validation",
    ),
    _SourceSpec(
        "src/nsqd/domain/operator_g_release_validation.py", "release_failure_record_validation"
    ),
    _SourceSpec("src/nsqd/domain/operator_g_types.py", "failure_record_contract_types"),
    _SourceSpec("src/nsqd/domain/operator_g_v1_validation.py", "legacy_record_validation"),
    _SourceSpec("src/nsqd/domain/snapshot.py", "canonical_snapshot_digest_runtime"),
    _SourceSpec("src/nsqd/infrastructure/operator_g_census.py", "bounded_census_orchestration"),
    _SourceSpec(
        "src/nsqd/infrastructure/operator_g_census_formats.py", "structured_format_discovery"
    ),
    _SourceSpec(
        "src/nsqd/infrastructure/operator_g_census_files.py", "race_safe_filesystem_boundary"
    ),
    _SourceSpec(
        "src/nsqd/infrastructure/operator_g_structured_inputs.py",
        "typed_structured_input_boundary",
    ),
)


def readiness_source_bindings(repository_root: Path) -> tuple[SourceBinding, ...]:
    return tuple(
        SourceBinding(
            spec.path,
            spec.role,
            hashlib.sha256((repository_root / spec.path).read_bytes()).hexdigest(),
        )
        for spec in SOURCE_SPECS
    )


def sealed_zero_matches(
    census: OperatorGCensus,
    readiness: Mapping[str, StructuredValue],
    source_bindings: Sequence[SourceBinding],
) -> bool:
    return census.substantiates_zero and readiness == project_zero_readiness(
        census, source_bindings
    )
