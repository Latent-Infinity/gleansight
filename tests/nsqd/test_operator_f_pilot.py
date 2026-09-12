from __future__ import annotations

import hashlib
import json

import nsqd.domain.operator_f_pilot as operator_f
from tests.nsqd.operator_f_pilot_support import (
    HISTORICAL_RESULT_DIGEST,
    HISTORICAL_RESULT_SHA256,
    REPO_ROOT,
    RESULT_PATH,
    SHUFFLE_SEED,
    SNAPSHOT_ID,
    _inputs,
    _records,
    canonical_result_digest,
    historical_operator_f_inputs,
)


def test_pilot_compares_three_tracks_without_inventing_missing_coordinates() -> None:
    # Given five observed candidate labels but only three registered-axis coordinates
    inputs = _inputs()

    # When the evaluation-only pilot runs
    result = operator_f.evaluate_operator_f_pilot(inputs)

    # Then all labels are accounted for while only coordinate-eligible rows enter cells
    assert result.total_record_count == 5
    assert result.candidate_observed_record_count == 5
    assert result.coordinate_eligible_record_ids == (
        "N11-FIN-02",
        "N11-FIN-03",
        "N11-FIN-04",
    )
    assert result.coordinate_ineligible_record_ids == ("N11-FIN-01", "N11-FIN-05")
    assert tuple(track.track_id for track in result.tracks) == (
        "current_registered_axes",
        "current_axes_plus_validation_target",
        "current_axes_plus_shuffled_validation_target",
    )
    assert tuple(track.occupied_cell_count for track in result.tracks) == (3, 3, 3)
    assert tuple(track.observed_cell_coverage for track in result.tracks) == (1.0, 1.0, 1.0)
    assert tuple(track.records_per_occupied_cell for track in result.tracks) == (1.0, 1.0, 1.0)
    assert result.held_out_archive_coverage_gain is None
    assert result.evidence_sufficient is False
    assert result.schema_admission_recommended is False
    assert result.runtime_authorized is False
    assert result.schema_mutation_authorized is False
    assert result.schema_admission_authorized is False


def test_pilot_shuffle_is_process_independent_and_bound_to_an_explicit_permutation() -> None:
    # Given the same records in opposite input orders
    forward = _inputs()
    reverse = _inputs(tuple(reversed(_records())))

    # When both pilots use the same SHA-256-derived cyclic control
    first = operator_f.evaluate_operator_f_pilot(forward)
    second = operator_f.evaluate_operator_f_pilot(reverse)

    # Then ordering and Python hash/random state cannot affect the control or digest
    assert first.shuffle.algorithm == "sha256_seeded_cyclic_rotation/v1"
    assert first.shuffle.seed == SHUFFLE_SEED
    assert first.shuffle.offset == 4
    assert first.shuffle.permutation == (
        operator_f.OperatorFShuffleAssignment(
            record_id="N11-FIN-01", receives_value_from_record_id="N11-FIN-05"
        ),
        operator_f.OperatorFShuffleAssignment(
            record_id="N11-FIN-02", receives_value_from_record_id="N11-FIN-01"
        ),
        operator_f.OperatorFShuffleAssignment(
            record_id="N11-FIN-03", receives_value_from_record_id="N11-FIN-02"
        ),
        operator_f.OperatorFShuffleAssignment(
            record_id="N11-FIN-04", receives_value_from_record_id="N11-FIN-03"
        ),
        operator_f.OperatorFShuffleAssignment(
            record_id="N11-FIN-05", receives_value_from_record_id="N11-FIN-04"
        ),
    )
    assert second.shuffle == first.shuffle
    assert second.result_digest == first.result_digest


def test_pilot_result_digest_matches_test_owned_canonical_oracle() -> None:
    # Given the sealed historical result bytes
    payload: dict[str, operator_f.JsonValue] = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    # When the canonical digest is independently computed with the standard library
    digest = canonical_result_digest(payload)

    # Then it matches the sealed historical result without calling production digest code
    assert digest == HISTORICAL_RESULT_DIGEST
    assert payload["result_digest"] == digest
    assert hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest() == HISTORICAL_RESULT_SHA256


def test_pilot_findings_derive_from_alternate_identities_counts_and_occupancy() -> None:
    # Given six source-bound records with alternate IDs, four eligible rows, and two base cells
    coordinates = operator_f.RegisteredAxisCoordinates
    records = tuple(
        record.model_copy(update={"record_id": f"ALT-{index}"})
        for index, record in enumerate(_records(), start=1)
    )
    records = (
        records[0].model_copy(
            update={
                "registered_coordinates": coordinates(
                    mechanism="shared", target="returns", horizon="daily"
                ),
                "validation_target": "representation_fidelity",
            }
        ),
        records[1].model_copy(
            update={
                "registered_coordinates": coordinates(
                    mechanism="shared", target="returns", horizon="daily"
                ),
                "validation_target": "predictive_task",
            }
        ),
        records[2].model_copy(
            update={
                "registered_coordinates": coordinates(
                    mechanism="shared", target="returns", horizon="daily"
                ),
                "validation_target": "economic_utility",
            }
        ),
        records[3].model_copy(
            update={
                "registered_coordinates": coordinates(
                    mechanism="distinct", target="risk", horizon="intraday"
                ),
                "validation_target": "calibrated_risk",
            }
        ),
        records[4],
        records[4].model_copy(update={"record_id": "ALT-6", "projection_sha256": "6" * 64}),
    )

    # When the report-only pilot evaluates the alternate corpus
    result = operator_f.evaluate_operator_f_pilot(_inputs(records))

    # Then findings describe its identities and each measured occupancy, not historical N11 facts
    assert result.coordinate_eligible_record_ids == ("ALT-1", "ALT-2", "ALT-3", "ALT-4")
    assert tuple(track.occupied_cell_count for track in result.tracks) == (2, 4, 3)
    assert result.findings == (
        "All six records have observed validation_target values; only ALT-1, ALT-2, ALT-3, "
        "and ALT-4 have registered-axis coordinates.",
        "The current_registered_axes track occupies two cells, the "
        "current_axes_plus_validation_target track occupies four cells, and the "
        "current_axes_plus_shuffled_validation_target track occupies three cells among four "
        "coordinate-eligible records; descriptive occupied-cell coverage is 0.5, 1.0, and "
        "0.75, with density 2.0, 1.0, and 1.3333333333333333 records per occupied cell.",
        "Held-out archive coverage gain is not estimable from four coordinate-eligible records; "
        "no stability or quality evidence is claimed.",
    )
    assert result.evidence_sufficient is False
    assert result.schema_admission_recommended is False
    assert result.runtime_authorized is False


def test_committed_pilot_binds_every_source_byte_and_preserves_non_authority() -> None:
    # Given the committed report-only pilot artifact
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    # When its shape, digest, and source bindings are validated
    trusted_inputs = historical_operator_f_inputs()
    result = operator_f.validate_operator_f_pilot_result(payload, trusted_inputs=trusted_inputs)

    # Then every declared source digest matches disk and no authority is inferred
    for binding in result.source_artifacts:
        source_path = REPO_ROOT / binding.path
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == binding.sha256
    assert result.proposal_id == "F-PROP-001"
    assert result.source_snapshot_id == SNAPSHOT_ID
    assert result.total_record_count == 5
    assert len(result.coordinate_eligible_record_ids) == 3
    assert result.evidence_sufficient is False
    assert result.schema_admission_recommended is False
    assert result.runtime_authorized is False
    assert result.schema_mutation_authorized is False
    assert result.schema_admission_authorized is False
