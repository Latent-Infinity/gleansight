from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from nsqd.domain.operator_g_census import CandidateEvidence, OperatorGCensus
from nsqd.domain.operator_g_types import StructuredValue

PREDECESSOR_MANIFEST: Final = (
    "../nsqd-operator-g-readiness-census-2026-09-12-contract-closure/packet-manifest.json"
)
PREDECESSOR_DIGEST: Final = "0649829a742d6433ec757afb5620cfa5f03665372d08196b47259a432bbb3f49"
CREATED_AT_UTC: Final = "2026-09-12T03:30:00Z"


@dataclass(frozen=True, slots=True)
class SourceBinding:
    path: str
    role: str
    sha256: str


def project_zero_readiness(
    census: OperatorGCensus, source_bindings: Sequence[SourceBinding]
) -> dict[str, StructuredValue]:
    configuration = census.configuration
    limits: dict[str, StructuredValue] = {
        "max_files": configuration.max_files,
        "max_file_bytes": configuration.max_file_bytes,
        "max_total_bytes": configuration.max_total_bytes,
        "max_depth": configuration.max_depth,
        "max_structured_depth": configuration.max_structured_depth,
    }
    census_value: dict[str, StructuredValue] = {}
    census_value["algorithm_version"] = census.algorithm_version
    census_value["status"] = census.status.value
    census_value["scope_snapshot_digest"] = census.scope_snapshot_digest
    census_value["scope_file_count"] = census.scope_file_count
    census_value["repository_roots"] = list(configuration.roots)
    census_value["structured_extensions"] = [
        suffix.removeprefix(".") for suffix in configuration.structured_suffixes
    ]
    census_value["limits"] = limits
    trust_inputs: dict[str, StructuredValue] = {
        "trusted_approval_count": census.trusted_approval_count,
        "trusted_evidence_artifact_count": census.trusted_evidence_artifact_count,
    }
    inventory: list[StructuredValue] = [
        {
            "candidate_class": item.candidate_class.value,
            "observed_count": item.observed_count,
            "qualifying_count": item.qualifying_count,
            "reason_code": item.reason_code.value,
        }
        for item in census.inventory
    ]
    result: dict[str, StructuredValue] = {}
    result.update(
        {
            "schema_version": 1,
            "packet_kind": "operator_g_readiness_census",
            "created_at_utc": CREATED_AT_UTC,
            "authorization_state": "report_only",
            "runtime_authorized": False,
            "resurrection_authorized": False,
            "operator_g_eligible": False,
            "evidence_sufficient": False,
            "predecessor": {
                "manifest": PREDECESSOR_MANIFEST,
                "packet_digest": PREDECESSOR_DIGEST,
            },
            "census": census_value,
            "external_trust_inputs": trust_inputs,
            "source_bindings": [
                {"path": binding.path, "role": binding.role, "sha256": binding.sha256}
                for binding in source_bindings
            ],
            "candidate_locators": _candidate_locators(census.candidates),
            "candidate_inventory": inventory,
            "qualifying_approved_record_count": len(census.qualifying_record_digests),
            "qualifying_record_digests": list(census.qualifying_record_digests),
            "records": [],
            "authority": {
                "packet_inclusion_authorized": False,
                "operator_g_eligibility_implied": False,
                "restart_authorized": False,
                "resurrection_authorized": False,
                "runtime_authorized": False,
            },
        }
    )
    return result


def _candidate_locators(candidates: Sequence[CandidateEvidence]) -> list[StructuredValue]:
    grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for candidate in candidates:
        path, separator, locator = str(candidate.locator).partition("#")
        key = (path, candidate.candidate_class.value, candidate.reason_code.value)
        grouped[key].append(locator if separator else "")
    result: list[StructuredValue] = []
    for (path, candidate_class, reason), locators in sorted(grouped.items()):
        result.append(
            {
                "locator": _compact_locator(path, locators),
                "candidate_class": candidate_class,
                "observed_count": len(locators),
                "reason_code": reason,
            }
        )
    return result


def _compact_locator(path: str, locators: Sequence[str]) -> str:
    expected = [str(index) for index in range(len(locators))]
    if len(locators) == 1:
        return f"{path}#{locators[0]}"
    if set(locators) == set(expected):
        return f"{path}#0..{len(locators) - 1}"
    return f"{path}#{','.join(locators)}"
