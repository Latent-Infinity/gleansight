"""Validated inputs to the local NSQD application workflows."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from gleansight.api.models import Identifier, Request

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SnapshotState = Literal["smoke_only", "calibration", "production_valid"]


class PageRequest(Request):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GetRequest(Request):
    id: Identifier


class SkeletonRequest(Request):
    candidate_fixture: Path
    axiom: Identifier


class HarvestRequest(Request):
    file: Path


class ProjectRequest(Request):
    projection: Path
    manifest: Path


class MapRequest(Request):
    snapshot_id: Identifier
    domain_policy_id: Identifier
    snapshot_state: SnapshotState = "calibration"
    window_days: int = Field(default=730, ge=1)


class DivergeRequest(MapRequest):
    candidate_fixture: Path
    axiom: Identifier
    operator: Literal["A", "B", "E"] = "A"
    target_cell_id: Identifier | None = None
    axiom_cell_id: Identifier | None = None

    @model_validator(mode="after")
    def require_transfer_cells(self) -> "DivergeRequest":
        if self.operator == "B" and (self.target_cell_id is None or self.axiom_cell_id is None):
            raise ValueError("Operator B requires target_cell_id and axiom_cell_id")
        return self


class GroundRequest(Request):
    candidate_artifact_hash: Digest
    snapshot_id: Identifier
    corpus_version: int = Field(ge=0)
    snapshot_state: SnapshotState = "calibration"


class GateRequest(GroundRequest):
    evaluator_run_id: Identifier


class RescoreRequest(Request):
    card_id: Identifier
    current_snapshot_id: Identifier
    current_corpus_version: int = Field(ge=0)
    snapshot_state: SnapshotState = "calibration"


class AcquireRequest(Request):
    snapshot_id: Identifier
    domain_policy_id: Identifier
    target: Literal["calibration", "production_valid"] = "calibration"
    human_decision: Literal["approve", "decline"] | None = None
    approved_projections: list[Path] = Field(default_factory=list, max_length=200)
    approval_manifest: Path | None = None

    @model_validator(mode="after")
    def require_manifest_pair(self) -> "AcquireRequest":
        if bool(self.approved_projections) != (self.approval_manifest is not None):
            raise ValueError("approved_projections and approval_manifest are required together")
        return self


class DigestRequest(Request):
    digest: Digest


class TauRequest(Request):
    candidate_artifact_hashes: list[Digest] = Field(min_length=1, max_length=200)


class TauEvaluateRequest(TauRequest):
    inputs: list[Path] = Field(min_length=1, max_length=200)
    require_balanced: bool = False


class VerdictRequest(Request):
    snapshot_id: Identifier
    domain_policy_id: Identifier
