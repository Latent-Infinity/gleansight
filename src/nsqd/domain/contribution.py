from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import JsonValue

from nsqd.domain.acquisition_portfolio import (
    Contract,
    Digest,
    StagedPortfolio,
    SufficiencyObservation,
    Text,
)
from nsqd.domain.policy import DomainPolicy


class FrozenProjectionInput(Contract):
    projection_path: Text
    manifest_path: Text
    files: dict[str, str]
    sha256: Digest


class ProjectionContribution(Contract):
    ordinal: int
    input: FrozenProjectionInput
    source_paper_id: str | None
    target_ids: tuple[Digest, ...]
    reviewed_projection_digest: Digest | None
    outcome: Literal["applied", "refused"]
    created: bool
    record_id: str | None
    before: SufficiencyObservation
    after: SufficiencyObservation
    refusal: str | None


class ContributionReport(Contract):
    staged: StagedPortfolio
    as_of: datetime
    policy: DomainPolicy
    policy_manifest_available: bool
    approved_harvest_seed_digests: frozenset[str]
    initial_records: tuple[dict[str, JsonValue], ...]
    initial_snapshot_members: tuple[str, ...]
    initial_snapshot_schema_version: int
    entries: tuple[ProjectionContribution, ...]
    interpretation: Literal["Observed correspondence, not causal source importance"] = (
        "Observed correspondence, not causal source importance"
    )
    grants_approval: Literal[False] = False


class ArtifactReference(Contract):
    bundle_path: Text
    sha256: Digest


class ReplayResult(Contract):
    verified: Literal[True] = True
    projections: int
    applied: int
    refused: int
    no_change: int
    grants_approval: Literal[False] = False
