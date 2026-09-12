from __future__ import annotations

import pytest

import nsqd.domain.operator_f_pilot as operator_f
from tests.nsqd.operator_f_pilot_support import _inputs, _records


@pytest.mark.parametrize("record_count", range(5))
def test_pilot_inputs_reject_fewer_than_five_records(record_count: int) -> None:
    # Given an explicitly sized source-bound record tuple below the report floor
    records = _records()[:record_count]

    # When/Then the typed input boundary parses it, evaluation remains unreachable
    with pytest.raises(ValueError, match="at least five uniquely identified records"):
        _inputs(records)


def test_pilot_inputs_do_not_replace_explicit_empty_records_with_defaults() -> None:
    # Given an explicitly empty record tuple
    records: tuple[operator_f.OperatorFPilotRecord, ...] = ()

    # When/Then it crosses the input boundary, the historical fixture is not substituted
    with pytest.raises(ValueError, match="at least five uniquely identified records"):
        _inputs(records)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("proposal_id", " ", "proposal_id"),
        ("shuffle_seed", " ", "shuffle_seed"),
        ("source_artifacts", [], "source artifact paths"),
        (
            "source_artifacts",
            [{"path": " ", "sha256": "a" * 64}],
            "path",
        ),
    ],
)
def test_pilot_inputs_reject_incomplete_identity_and_source_bindings(
    field: str,
    value: operator_f.JsonValue,
    message: str,
) -> None:
    # Given otherwise valid pilot input data
    payload = _inputs().model_dump(mode="python")
    payload[field] = value

    # When/Then the boundary parses it, no evaluable typed input is produced
    with pytest.raises(ValueError, match=message):
        operator_f.OperatorFPilotInputs.model_validate(payload)


def test_pilot_rejects_duplicate_or_unbound_projection_records() -> None:
    # Given duplicated records and a projection digest absent from source bindings
    duplicate = _inputs().model_dump(mode="python")
    duplicate["records"] = [duplicate["records"][0], duplicate["records"][0]]
    unbound = _inputs().model_dump(mode="python")
    unbound["records"][0]["projection_sha256"] = "c" * 64

    # When/Then either input crosses the boundary, neither can reach evaluation
    with pytest.raises(ValueError, match="uniquely identified records"):
        operator_f.OperatorFPilotInputs.model_validate(duplicate)
    with pytest.raises(ValueError, match="bind source artifact digests"):
        operator_f.OperatorFPilotInputs.model_validate(unbound)


def test_pilot_rejects_a_corpus_without_registered_axis_coordinates() -> None:
    # Given source-bound records whose approved projections have no coordinates
    records = tuple(
        record.model_copy(update={"registered_coordinates": None}) for record in _records()
    )
    inputs = _inputs(records)

    # When/Then comparison is requested, the evaluator does not invent coordinates
    with pytest.raises(ValueError, match="coordinates for at least one record"):
        operator_f.evaluate_operator_f_pilot(inputs)
