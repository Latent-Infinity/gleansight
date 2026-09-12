from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

import pydantic
import yaml

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_pilot_support import (
    HISTORICAL_RESULT_SHA256,
    historical_operator_f_inputs,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
READINESS_PATH: Final = (
    REPO_ROOT / "docs/reviews/nsqd-operator-f-readiness-2026-09-08/readiness.json"
)
PILOT_PATH: Final = (
    REPO_ROOT
    / "docs/reviews/nsqd-operator-activation-2026-08-30/operator-f-validation-target-pilot.json"
)
PROJECTION_ROOT: Final = REPO_ROOT / "docs/reviews/nsqd-projection-review-2026-08-28/final"
READINESS_SHA256: Final = "a1af10fcccd421aa2491ca6d75fba6bf29c127585bf7031adc367b4dc4c511dd"


class _FrozenModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, strict=True, extra="ignore")


class _Paper(_FrozenModel):
    record_id: str
    source_paper_id: str


class _Inventory(_FrozenModel):
    independent_source_papers: tuple[_Paper, ...]


class _Readiness(_FrozenModel):
    authorization_state: str
    runtime_authorized: bool
    schema_admission_authorized: bool
    evidence_sufficient: bool
    approval_scope: str
    inventory: _Inventory


class _Projection(_FrozenModel):
    id: str
    source_paper_id: str
    source_excerpt_path: str
    source_markdown_sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_current_readiness_inputs() -> operator_f.OperatorFHistoricalReadinessInputs:
    pilot = historical_operator_f_inputs()
    assert _sha256(READINESS_PATH) == READINESS_SHA256
    assert _sha256(PILOT_PATH) == HISTORICAL_RESULT_SHA256
    readiness = _Readiness.model_validate_json(READINESS_PATH.read_text(encoding="utf-8"))
    papers = {
        paper.record_id: paper.source_paper_id
        for paper in readiness.inventory.independent_source_papers
    }
    groups: list[operator_f.OperatorFHistoricalSourceGroup] = []
    for record in pilot.records:
        projection_path = PROJECTION_ROOT / f"{record.record_id}.yaml"
        projection = _Projection.model_validate(
            yaml.safe_load(projection_path.read_text(encoding="utf-8"))
        )
        excerpt_path = PROJECTION_ROOT / projection.source_excerpt_path
        assert projection.id == record.record_id
        assert projection.source_paper_id == papers[record.record_id]
        assert _sha256(projection_path) == record.projection_sha256
        assert _sha256(excerpt_path) == projection.source_markdown_sha256
        coordinates = None
        if record.registered_coordinates is not None:
            coordinates = operator_f.RegisteredCoordinates.model_validate(
                record.registered_coordinates.model_dump(mode="python")
            )
        groups.append(
            operator_f.OperatorFHistoricalSourceGroup(
                record_id=record.record_id,
                canonical_work_identity=projection.source_paper_id,
                approved_projection_sha256=record.projection_sha256,
                approved_excerpt_sha256=projection.source_markdown_sha256,
                registered_coordinates=coordinates,
                validation_target=record.validation_target,
            )
        )
    return operator_f.OperatorFHistoricalReadinessInputs(
        readiness_sha256=READINESS_SHA256,
        historical_pilot_result_sha256=HISTORICAL_RESULT_SHA256,
        authorization_state=readiness.authorization_state,
        approval_scope=readiness.approval_scope,
        runtime_authorized=readiness.runtime_authorized,
        schema_admission_authorized=readiness.schema_admission_authorized,
        evidence_sufficient=readiness.evidence_sufficient,
        successor_approvals_available=False,
        source_groups=tuple(groups),
    )
