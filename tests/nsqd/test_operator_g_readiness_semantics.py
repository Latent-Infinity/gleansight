from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from nsqd.domain.operator_g_census import StructuredValue
from nsqd.domain.operator_g_readiness import (
    project_zero_readiness,
    readiness_source_bindings,
    sealed_zero_matches,
)
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from tests.nsqd.operator_g_census_support import census_contract, mapping

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Mutation:
    claim: str
    path: tuple[str | int, ...]
    value: StructuredValue


MUTATIONS = (
    Mutation("schema", ("schema_version",), 2),
    Mutation("kind", ("packet_kind",), "forged"),
    Mutation("created", ("created_at_utc",), "2026-09-09T00:00:00Z"),
    Mutation("inventory count", ("candidate_inventory", 3, "observed_count"), 2),
    Mutation("inventory reason", ("candidate_inventory", 3, "reason_code"), "forged"),
    Mutation("locator", ("candidate_locators", 0, "locator"), "docs/forged.json#0"),
    Mutation("locator count", ("candidate_locators", 1, "observed_count"), 2),
    Mutation("roots", ("census", "repository_roots"), ["docs"]),
    Mutation("extensions", ("census", "structured_extensions"), ["json"]),
    Mutation("limits", ("census", "limits", "max_files"), 1),
    Mutation("approval trust count", ("external_trust_inputs", "trusted_approval_count"), 1),
    Mutation(
        "evidence trust count",
        ("external_trust_inputs", "trusted_evidence_artifact_count"),
        1,
    ),
    Mutation("packet inclusion", ("authority", "packet_inclusion_authorized"), True),
    Mutation("eligibility", ("authority", "operator_g_eligibility_implied"), True),
    Mutation("restart", ("authority", "restart_authorized"), True),
    Mutation("resurrection", ("authority", "resurrection_authorized"), True),
    Mutation("runtime", ("authority", "runtime_authorized"), True),
    Mutation("records", ("records",), [{"failure_record_id": "forged"}]),
    Mutation("evidence", ("evidence_sufficient",), True),
    Mutation("predecessor path", ("predecessor", "manifest"), "../forged.json"),
    Mutation("predecessor digest", ("predecessor", "packet_digest"), "0" * 64),
    Mutation("source path", ("source_bindings", 0, "path"), "docs/forged.json"),
    Mutation("source role", ("source_bindings", 0, "role"), "forged"),
    Mutation("source hash", ("source_bindings", 0, "sha256"), "0" * 64),
    Mutation("qualifying count", ("qualifying_approved_record_count",), 1),
    Mutation("qualifying digest", ("qualifying_record_digests",), ["0" * 64]),
)


def _mutate(
    value: StructuredValue, path: Sequence[str | int], replacement: StructuredValue
) -> None:
    assert path
    cursor = value
    for segment in path[:-1]:
        cursor = (
            mapping(cursor)[segment] if isinstance(segment, str) else _sequence(cursor)[segment]
        )
    final = path[-1]
    if isinstance(final, str):
        mapping(cursor)[final] = replacement
    else:
        _sequence(cursor)[final] = replacement


def _sequence(value: StructuredValue) -> list[StructuredValue]:
    assert isinstance(value, list)
    return value


def _remanifest(packet: dict[str, StructuredValue]) -> str:
    payload = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda item: item.claim)
def test_remanifested_material_claim_mutation_fails_semantic_validation(
    mutation: Mutation,
) -> None:
    census = census_operator_g_evidence(REPO_ROOT, contract=census_contract())
    bindings = readiness_source_bindings(REPO_ROOT)
    packet = copy.deepcopy(project_zero_readiness(census, bindings))
    original_manifest = _remanifest(packet)
    _mutate(packet, mutation.path, mutation.value)

    assert _remanifest(packet) != original_manifest
    assert sealed_zero_matches(census, packet, bindings) is False
