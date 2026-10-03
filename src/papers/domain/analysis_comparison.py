"""Read-only analysis inspection and explicitly selected evaluation cohorts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

type Identity = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ComparisonModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunPair(ComparisonModel):
    baseline_run_id: Identity
    revised_run_id: Identity

    @model_validator(mode="after")
    def distinct(self) -> RunPair:
        if self.baseline_run_id == self.revised_run_id:
            message = "Choose two distinct analysis runs."
            raise ValueError(message)
        return self


class ArtifactView(ComparisonModel):
    path: str | None
    state: Literal["available", "empty", "absent", "unavailable"]
    text: str | None = None
    sha256: str | None = None
    error: str | None = None


class ExtractedValue(ComparisonModel):
    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: float | None
    value_boolean: int | None

    @property
    def identity(self) -> tuple[str, str | None, str]:
        return self.entity_type, self.entity_ref, self.field_path


class RunInspection(ComparisonModel):
    run_id: str
    paper_id: str
    prompt_version_id: str
    profile_id: str
    model_name: str
    status: str
    error_message: str | None
    validation_issues: JsonValue
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    cost_status: Literal["recorded", "unknown"]
    extraction_schema: JsonValue
    output_md: ArtifactView
    output_json: ArtifactView
    extractions: tuple[ExtractedValue, ...]


class ExtractionDifference(ComparisonModel):
    entity_type: str
    entity_ref: str | None
    field_path: str
    change: Literal["unchanged", "changed", "missing_baseline", "missing_revised"]
    baseline: ExtractedValue | None
    revised: ExtractedValue | None


class RunComparison(ComparisonModel):
    baseline: RunInspection
    revised: RunInspection
    schema_changed: bool
    schema_diff: str
    output_diff: str
    json_output_diff: str
    extraction_diff: tuple[ExtractionDifference, ...]
    interpretation: str = "Inspection only; no quality ranking or acceptance decision."


class CohortSelection(ComparisonModel):
    name: Identity
    project_id: Identity | None = None
    baseline_prompt_version_id: Identity
    revised_prompt_version_id: Identity
    pairs: Annotated[tuple[RunPair, ...], Field(min_length=1, max_length=100)]


class PinnedComparison(ComparisonModel):
    pair: RunPair
    paper_id: str
    baseline_sha256: str
    revised_sha256: str


class SavedCohort(ComparisonModel):
    cohort_id: str
    created_at: str
    selection: CohortSelection
    runs: tuple[PinnedComparison, ...]
    fingerprint_version: Literal[1, 2] = 1


class CohortReport(ComparisonModel):
    cohort: SavedCohort
    comparisons: tuple[RunComparison, ...]
