from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Annotated, Literal, Self

import pydantic

from nsqd.domain.operator_f_pilot_findings import derive_pilot_findings
from nsqd.domain.snapshot import canonical_json, sha256_hex

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _strict_false(value: JsonValue) -> JsonValue:
    if value is not False:
        raise ValueError("value must be boolean false")
    return value


def _strict_one(value: JsonValue) -> JsonValue:
    if type(value) is not int:
        raise ValueError("value must be integer one")
    return value


def _finite_float(value: JsonValue) -> JsonValue:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("value must be a finite float")
    return value


Sha256 = Annotated[pydantic.StrictStr, pydantic.Field(pattern=r"^[0-9a-f]{64}$")]
NonBlankStr = Annotated[pydantic.StrictStr, pydantic.Field(pattern=r"\S")]
FiniteFloat = Annotated[pydantic.StrictFloat, pydantic.BeforeValidator(_finite_float)]
StrictFalse = Annotated[Literal[False], pydantic.BeforeValidator(_strict_false)]
StrictOne = Annotated[Literal[1], pydantic.BeforeValidator(_strict_one)]
ValidationTarget = Literal[
    "representation_fidelity",
    "predictive_task",
    "economic_utility",
    "calibrated_risk",
]
TrackId = Literal[
    "current_registered_axes",
    "current_axes_plus_validation_target",
    "current_axes_plus_shuffled_validation_target",
]


class _FrozenModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")


class RegisteredAxisCoordinates(_FrozenModel):
    mechanism: NonBlankStr
    target: NonBlankStr
    horizon: NonBlankStr


class OperatorFSourceArtifact(_FrozenModel):
    path: NonBlankStr
    sha256: Sha256


class OperatorFPilotRecord(_FrozenModel):
    record_id: NonBlankStr
    projection_sha256: Sha256
    registered_coordinates: RegisteredAxisCoordinates | None
    validation_target: ValidationTarget


class OperatorFPilotInputs(_FrozenModel):
    proposal_id: NonBlankStr
    approved_proposal_digest: Sha256
    source_snapshot_id: Sha256
    source_artifacts: tuple[OperatorFSourceArtifact, ...]
    records: tuple[OperatorFPilotRecord, ...]
    shuffle_seed: NonBlankStr

    @pydantic.model_validator(mode="after")
    def require_unique_nonempty_inputs(self) -> Self:
        record_ids = tuple(record.record_id for record in self.records)
        source_paths = tuple(source.path for source in self.source_artifacts)
        if len(record_ids) < 5 or len(record_ids) != len(set(record_ids)):
            msg = "operator F pilot requires at least five uniquely identified records"
            raise ValueError(msg)
        if not source_paths or len(source_paths) != len(set(source_paths)):
            msg = "operator F pilot source artifact paths must be non-empty and unique"
            raise ValueError(msg)
        source_digests = {source.sha256 for source in self.source_artifacts}
        if any(record.projection_sha256 not in source_digests for record in self.records):
            msg = "operator F pilot record projections must bind source artifact digests"
            raise ValueError(msg)
        return self


class OperatorFShuffleAssignment(_FrozenModel):
    record_id: NonBlankStr
    receives_value_from_record_id: NonBlankStr


class OperatorFShuffleDefinition(_FrozenModel):
    algorithm: Literal["sha256_seeded_cyclic_rotation/v1"]
    seed: NonBlankStr
    offset: pydantic.StrictInt
    permutation: tuple[OperatorFShuffleAssignment, ...]


class OperatorFTrackMetrics(_FrozenModel):
    track_id: TrackId
    eligible_record_count: pydantic.StrictInt
    occupied_cell_count: pydantic.StrictInt
    occupied_cells: tuple[pydantic.StrictStr, ...]
    observed_cell_coverage: FiniteFloat
    records_per_occupied_cell: FiniteFloat
    occupied_cell_gain_vs_current: pydantic.StrictInt


class OperatorFPilotResult(_FrozenModel):
    schema_version: StrictOne
    record_type: Literal["operator_f_axis_pilot_result"]
    authorization_state: Literal["report_only"]
    evaluation_scope: Literal["evaluation_only"]
    runtime_authorized: StrictFalse
    schema_mutation_authorized: StrictFalse
    schema_admission_authorized: StrictFalse
    proposal_id: NonBlankStr
    approved_proposal_digest: Sha256
    source_snapshot_id: Sha256
    source_artifacts: tuple[OperatorFSourceArtifact, ...]
    registered_axes: tuple[Literal["mechanism"], Literal["target"], Literal["horizon"]]
    candidate_axis: Literal["validation_target"]
    records: tuple[OperatorFPilotRecord, ...]
    total_record_count: pydantic.StrictInt
    candidate_observed_record_count: pydantic.StrictInt
    coordinate_eligible_record_ids: tuple[NonBlankStr, ...]
    coordinate_ineligible_record_ids: tuple[NonBlankStr, ...]
    shuffle: OperatorFShuffleDefinition
    tracks: tuple[OperatorFTrackMetrics, OperatorFTrackMetrics, OperatorFTrackMetrics]
    held_out_archive_coverage_gain: None
    findings: tuple[pydantic.StrictStr, ...]
    evidence_sufficient: StrictFalse
    schema_admission_recommended: StrictFalse
    result_digest: Sha256


def evaluate_operator_f_pilot(inputs: OperatorFPilotInputs) -> OperatorFPilotResult:
    records = tuple(sorted(inputs.records, key=lambda record: record.record_id))
    eligible = tuple(record for record in records if record.registered_coordinates is not None)
    if not eligible:
        msg = "operator F pilot requires registered-axis coordinates for at least one record"
        raise ValueError(msg)
    offset = 1 + int.from_bytes(
        hashlib.sha256(inputs.shuffle_seed.encode("utf-8")).digest()[:8], "big"
    ) % (len(records) - 1)
    permutation = tuple(
        OperatorFShuffleAssignment(
            record_id=record.record_id,
            receives_value_from_record_id=records[(index + offset) % len(records)].record_id,
        )
        for index, record in enumerate(records)
    )
    values: dict[str, ValidationTarget] = {
        record.record_id: record.validation_target for record in records
    }
    shuffled: dict[str, ValidationTarget] = {
        assignment.record_id: values[assignment.receives_value_from_record_id]
        for assignment in permutation
    }
    current_cells = _occupied_cells(eligible, candidate_values=None)
    candidate_cells = _occupied_cells(eligible, candidate_values=values)
    control_cells = _occupied_cells(eligible, candidate_values=shuffled)
    counts = (len(eligible), len(current_cells))
    tracks = (
        _track("current_registered_axes", current_cells, counts),
        _track(
            "current_axes_plus_validation_target",
            candidate_cells,
            counts,
        ),
        _track(
            "current_axes_plus_shuffled_validation_target",
            control_cells,
            counts,
        ),
    )
    eligible_record_ids = tuple(record.record_id for record in eligible)
    findings = derive_pilot_findings(len(records), eligible_record_ids, tracks)
    payload = {
        "schema_version": 1,
        "record_type": "operator_f_axis_pilot_result",
        "authorization_state": "report_only",
        "evaluation_scope": "evaluation_only",
        "runtime_authorized": False,
        "schema_mutation_authorized": False,
        "schema_admission_authorized": False,
        "proposal_id": inputs.proposal_id,
        "approved_proposal_digest": inputs.approved_proposal_digest,
        "source_snapshot_id": inputs.source_snapshot_id,
        "source_artifacts": inputs.source_artifacts,
        "registered_axes": ("mechanism", "target", "horizon"),
        "candidate_axis": "validation_target",
        "records": records,
        "total_record_count": len(records),
        "candidate_observed_record_count": len(records),
        "coordinate_eligible_record_ids": eligible_record_ids,
        "coordinate_ineligible_record_ids": tuple(
            record.record_id for record in records if record.registered_coordinates is None
        ),
        "shuffle": OperatorFShuffleDefinition(
            algorithm="sha256_seeded_cyclic_rotation/v1",
            seed=inputs.shuffle_seed,
            offset=offset,
            permutation=permutation,
        ),
        "tracks": tracks,
        "held_out_archive_coverage_gain": None,
        "findings": findings,
        "evidence_sufficient": False,
        "schema_admission_recommended": False,
        "result_digest": "0" * 64,
    }
    provisional = OperatorFPilotResult.model_validate(payload)
    result_digest = _result_digest(provisional.model_dump(mode="json"))
    return provisional.model_copy(update={"result_digest": result_digest})


def validate_operator_f_pilot_result(
    payload: dict[str, JsonValue],
    *,
    trusted_inputs: OperatorFPilotInputs,
) -> OperatorFPilotResult:
    """Validate against caller-trusted bindings, which this function does not approve."""
    try:
        result = OperatorFPilotResult.model_validate(payload)
    except pydantic.ValidationError as exc:
        msg = "operator F pilot result shape is invalid"
        raise ValueError(msg) from exc
    if result.result_digest != _result_digest(result.model_dump(mode="json")):
        msg = "operator F pilot result digest does not match"
        raise ValueError(msg)
    expected = evaluate_operator_f_pilot(trusted_inputs)
    if result != expected:
        msg = "operator F pilot result does not match trusted inputs"
        raise ValueError(msg)
    return result


def _occupied_cells(
    records: tuple[OperatorFPilotRecord, ...],
    *,
    candidate_values: Mapping[str, ValidationTarget] | None,
) -> tuple[str, ...]:
    cells: set[str] = set()
    for record in records:
        coordinates = record.registered_coordinates
        if coordinates is None:
            continue
        cell = (
            f"mechanism={coordinates.mechanism}|target={coordinates.target}|"
            f"horizon={coordinates.horizon}"
        )
        if candidate_values is not None:
            cell = f"{cell}|validation_target={candidate_values[record.record_id]}"
        cells.add(cell)
    return tuple(sorted(cells))


def _track(
    track_id: TrackId,
    cells: tuple[str, ...],
    counts: tuple[int, int],
) -> OperatorFTrackMetrics:
    occupied_count = len(cells)
    return OperatorFTrackMetrics(
        track_id=track_id,
        eligible_record_count=counts[0],
        occupied_cell_count=occupied_count,
        occupied_cells=cells,
        observed_cell_coverage=occupied_count / counts[0],
        records_per_occupied_cell=counts[0] / occupied_count,
        occupied_cell_gain_vs_current=occupied_count - counts[1],
    )


def _result_digest(payload: dict[str, JsonValue]) -> str:
    preimage = dict(payload)
    preimage["result_digest"] = None
    return sha256_hex(canonical_json(preimage))
