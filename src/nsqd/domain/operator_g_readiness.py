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
        "docs/reviews/nsqd-operator-activation-2026-08-30/failure-record-contract.yaml",
        "canonical_failure_record_contract",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-08-30/operator-g.yaml",
        "current_operator_g_plan",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-tau-calibration-2026-08-29/candidate-hashes.json",
        "candidate_hash_reconciliation",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-tau-calibration-2026-08-29/candidates.json",
        "unexecuted_candidate_studies",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-tau-calibration-2026-08-29/measurements.jsonl",
        "tau_measurement_rows",
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
    _SourceSpec(
        "src/nsqd/domain/operator_g_record_validation.py",
        "canonical_failure_record_validation",
    ),
    _SourceSpec("src/nsqd/domain/operator_g_readiness.py", "readiness_projection_validator"),
    _SourceSpec(
        "src/nsqd/domain/operator_g_readiness_projection.py", "readiness_projection_builder"
    ),
    _SourceSpec(
        "src/nsqd/domain/operator_g_release_validation.py", "release_failure_record_validation"
    ),
    _SourceSpec("src/nsqd/domain/operator_g_types.py", "failure_record_contract_types"),
    _SourceSpec("src/nsqd/domain/operator_g_v1_validation.py", "legacy_record_validation"),
    _SourceSpec("src/nsqd/domain/snapshot.py", "canonical_snapshot_digest_runtime"),
    _SourceSpec("src/nsqd/infrastructure/operator_g_census.py", "bounded_census_orchestration"),
    _SourceSpec(
        "src/nsqd/infrastructure/operator_g_census_formats.py",
        "structured_format_discovery",
    ),
    _SourceSpec(
        "src/nsqd/infrastructure/operator_g_census_files.py",
        "race_safe_filesystem_boundary",
    ),
    _SourceSpec(
        "src/nsqd/infrastructure/operator_g_structured_inputs.py",
        "typed_structured_input_boundary",
    ),
    _SourceSpec("tests/nsqd/operator_dg_contract_support.py", "ast_only_synthetic_pending_fixture"),
    _SourceSpec(
        "docs/reviews/nsqd-operator-g-failure-record-contract-2026-09-11-v2/failure-record-contract-v2.yaml",
        "current_operator_g_failure_record_contract",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction/packet-manifest.json",
        "current_operator_c_evidence_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction/technical-review-summary.json",
        "operator_c_successor_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction/technical-review-seal.json",
        "operator_c_successor_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-f-readiness-2026-09-11-formula-correction/packet-manifest.json",
        "current_operator_f_readiness_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-f-readiness-2026-09-11-formula-correction/technical-review-summary.json",
        "operator_f_successor_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-f-readiness-2026-09-11-formula-correction/technical-review-seal.json",
        "operator_f_successor_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-status-window-calendar-replay-2026-09-11-command-sync/packet-manifest.json",
        "current_status_window_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-status-window-calendar-replay-2026-09-11-command-sync/technical-review-summary.json",
        "status_successor_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-status-window-calendar-replay-2026-09-11-command-sync/technical-review-seal.json",
        "status_successor_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-09-11-remediation/packet-manifest.json",
        "current_operator_activation_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-09-11-remediation/technical-review-summary.json",
        "activation_successor_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-09-11-remediation/technical-review-seal.json",
        "activation_successor_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup/packet-manifest.json",
        "reviewed_operator_g_predecessor_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup/technical-review-summary.json",
        "operator_g_predecessor_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup/technical-review-seal.json",
        "operator_g_predecessor_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/packet-manifest.json",
        "current_operator_f_implementation_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/technical-review-summary.json",
        "operator_f_implementation_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/technical-review-seal.json",
        "operator_f_implementation_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/packet-manifest.json",
        "current_operator_activation_manifest",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/technical-review-summary.json",
        "activation_pointer_sync_technical_review",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/technical-review-seal.json",
        "activation_pointer_sync_technical_review_seal",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-contract-closure/readiness.json",
        "operator_g_predecessor_readiness",
    ),
    _SourceSpec(
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-contract-closure/packet-manifest.json",
        "operator_g_predecessor_manifest",
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
