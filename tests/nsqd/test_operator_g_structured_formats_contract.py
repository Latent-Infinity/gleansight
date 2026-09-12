from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from nsqd.domain.operator_g_census import CensusStatus
from nsqd.domain.operator_g_types import StructuredValue
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from nsqd.infrastructure.operator_g_census_formats import (
    CalibrationFile,
    StructuredFormatError,
    all_mappings,
    derive_calibrations,
    normalize,
    parse_documents,
    record_candidates,
)
from nsqd.infrastructure.operator_g_structured_inputs import (
    NonStringMappingInput,
    UnsupportedStructuredInput,
    parse_structured_input,
)
from tests.nsqd.operator_g_census_support import census_contract, initialize_repository


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        ("value.json", b'{"name":"caf\\u00e9"}', [{"name": "caf\u00e9"}]),
        ("value.jsonl", b'{"row":1}\n\n {"row":2}\n', [{"row": 1}, {"row": 2}]),
        ("value.toml", b'name = "caf\xc3\xa9"\n', [{"name": "caf\u00e9"}]),
        ("value.yaml", b'name: "caf\xc3\xa9"\n', [{"name": "caf\u00e9"}]),
        ("value.yml", b"items:\n  - one\n  - 2\n", [{"items": ["one", 2]}]),
    ],
)
def test_documents_preserve_supported_format_values(
    path: str, content: bytes, expected: list[StructuredValue]
) -> None:
    # Given: UTF-8 structured content in a supported format
    # When: the decoder boundary parses and normalizes it
    documents = parse_documents(path, content)
    # Then: document order and nested values are preserved
    assert documents == expected


def test_unknown_suffix_uses_yaml_fallback() -> None:
    # Given: YAML content under an unrecognized suffix
    # When: the decoder boundary selects its fallback
    documents = parse_documents("value.data", b"enabled: true\n")
    # Then: YAML semantics are retained
    assert documents == [{"enabled": True}]


def test_empty_documents_and_blank_jsonl_keep_distinct_shapes() -> None:
    # Given: an empty YAML document and a JSONL stream containing only blank lines
    # When: both are parsed
    empty_document = parse_documents("empty.yaml", b"")
    blank_stream = parse_documents("blank.jsonl", b" \n\t\n")
    # Then: YAML has one null document while JSONL has no documents
    assert empty_document == [None]
    assert blank_stream == []


def test_empty_toml_is_one_mapping_and_empty_json_is_malformed() -> None:
    # Given: empty content under TOML and JSON suffixes
    # When: each decoder applies its native empty-document behavior
    empty_toml = parse_documents("empty.toml", b"")
    with pytest.raises(StructuredFormatError) as empty_json:
        parse_documents("empty.json", b"")
    # Then: TOML retains one mapping while JSON retains its syntax failure
    assert empty_toml == [{}]
    assert str(empty_json.value) == "empty.json: Expecting value: line 1 column 1 (char 0)"
    assert isinstance(empty_json.value.__cause__, json.JSONDecodeError)


def test_temporal_values_normalize_to_iso_strings() -> None:
    # Given: all temporal variants emitted by YAML and TOML
    values = [date(2026, 9, 8), datetime(2026, 9, 8, 1, 2, 3), time(1, 2, 3)]
    # When: direct values cross the normalization boundary
    normalized = normalize(values)
    # Then: each value uses its existing deterministic ISO representation
    assert normalized == ["2026-09-08", "2026-09-08T01:02:03", "01:02:03"]


def test_closed_input_parser_preserves_supported_recursive_values() -> None:
    # Given: a nested direct-test value containing temporal and scalar variants
    value = {"outer": [date(2026, 9, 8), None, True, 3, 1.5, "x"]}
    # When: the open decoder result is narrowed into the closed input union
    parsed = parse_structured_input(value)
    # Then: supported values remain structurally unchanged
    assert parsed == value


@pytest.mark.parametrize(
    ("value", "value_type"),
    [(b"x", "bytes"), ({"x"}, "set"), (("x", 1), "tuple")],
)
def test_closed_input_parser_tags_rejected_value_types(
    value: bytes | set[str] | tuple[str, int], value_type: str
) -> None:
    # Given: a direct-test value outside the normalized structured-value union
    # When: it is narrowed at the boundary
    parsed = parse_structured_input(value)
    # Then: the rejection is represented by a closed tagged variant
    assert parsed == UnsupportedStructuredInput(value_type)


def test_closed_input_parser_tags_non_string_mapping_keys() -> None:
    # Given: a mapping that cannot become a StructuredValue mapping
    # When: it is narrowed at the boundary
    parsed = parse_structured_input({1: "value"})
    # Then: the key rejection is represented explicitly
    assert parsed == NonStringMappingInput()


@pytest.mark.parametrize(
    ("value", "reason", "cause_name"),
    [
        (b"x", "unsupported structured value type: bytes", "_UnsupportedStructuredValueError"),
        ({"x"}, "unsupported structured value type: set", "_UnsupportedStructuredValueError"),
        (("x",), "unsupported structured value type: tuple", "_UnsupportedStructuredValueError"),
        ({1: "x"}, "non-string mapping key", "YAMLError"),
    ],
)
def test_direct_rejections_preserve_error_text_and_chaining(
    value: bytes | set[str] | tuple[str] | dict[int, str], reason: str, cause_name: str
) -> None:
    # Given: an unsupported direct normalization input
    # When: normalization rejects it
    with pytest.raises(StructuredFormatError) as captured:
        normalize(value)
    # Then: the public message and chained cause remain stable
    assert str(captured.value) == f"<value>: {reason}"
    assert type(captured.value.__cause__).__name__ == cause_name


def test_malformed_syntax_and_unicode_preserve_decoder_causes() -> None:
    # Given: malformed JSON syntax and malformed UTF-8 bytes
    cases = (("bad.json", b'{"x":}'), ("bad.yaml", b"\xff\xfe"))
    # When/Then: each failure retains its path, reason, and decoder cause
    with pytest.raises(StructuredFormatError) as syntax:
        parse_documents(*cases[0])
    with pytest.raises(StructuredFormatError) as unicode:
        parse_documents(*cases[1])
    assert str(syntax.value) == "bad.json: Expecting value: line 1 column 6 (char 5)"
    assert isinstance(syntax.value.__cause__, json.JSONDecodeError)
    assert str(unicode.value).startswith("bad.yaml: 'utf-8' codec can't decode byte 0xff")
    assert isinstance(unicode.value.__cause__, UnicodeDecodeError)


def test_depth_boundary_is_inclusive_and_preserves_error() -> None:
    # Given: one value at the configured depth and one level beyond it
    accepted = {"outer": {"value": 1}}
    rejected = {"outer": {"inner": {"value": 1}}}
    # When/Then: the limit remains inclusive and excess nesting keeps its message
    assert normalize(accepted, max_depth=2) == accepted
    with pytest.raises(StructuredFormatError) as captured:
        normalize(rejected, max_depth=2)
    assert str(captured.value) == "<value>: structured nesting exceeds depth 2"
    assert type(captured.value.__cause__).__name__ == "_NestingLimitError"


def test_mapping_walk_and_record_candidates_preserve_sorted_depth_first_order() -> None:
    # Given: mappings inserted in reverse lexical order with nested record candidates
    value = {
        "z": {"failure_record_id": "z"},
        "a": [{"record_type": "approved_failed_experiment"}],
    }
    # When: mappings and candidates are traversed
    mappings = [locator for locator, _ in all_mappings(value, "root")]
    candidates = [locator for locator, _ in record_candidates(value, "root")]
    # Then: traversal remains sorted and depth-first
    assert mappings == ["root", "root/a/0", "root/z"]
    assert candidates == ["root/a/0", "root/z"]


def test_registered_source_class_metadata_is_not_a_failure_record_candidate() -> None:
    value = {"source_class": "registered_experiment_artifact"}

    assert list(record_candidates(value, "root")) == []


def test_calibration_counts_and_reconciliation_remain_stable() -> None:
    # Given: one complete calibration root with matching IDs, pairs, and packet digest
    root = "docs/reviews/nsqd-tau-calibration-contract"
    candidates = json.dumps({"candidates": [{"id": "candidate-1"}]}, sort_keys=True).encode()
    measurements = (
        b'{"candidate_artifact_hash":"hash-1","measurement_artifact_digest":"digest-1"}\n'
    )
    hashes = json.dumps(
        {
            "candidate_packet_sha256": hashlib.sha256(candidates).hexdigest(),
            "hashes": [
                {
                    "candidate_id": "candidate-1",
                    "candidate_artifact_hash": "hash-1",
                    "measurement_artifact_digest": "digest-1",
                }
            ],
        }
    ).encode()
    files = tuple(
        CalibrationFile(f"{root}/{name}", content, hashlib.sha256(content).hexdigest())
        for name, content in (
            ("measurements.jsonl", measurements),
            ("candidates.json", candidates),
            ("candidate-hashes.json", hashes),
        )
    )
    # When: calibration inventory is derived
    result = derive_calibrations(files, 64)
    # Then: counts, paths, and reconciliation are unchanged
    assert len(result) == 1
    assert result[0].measurement_count == 1
    assert result[0].study_count == 1
    assert result[0].reconciled is True


def test_structured_rejection_keeps_census_incomplete(tmp_path: Path) -> None:
    # Given: a YAML value the normalized union rejects
    initialize_repository(tmp_path)
    (tmp_path / "docs" / "unsupported.yaml").write_text("value: !!binary SGVsbG8=\n")
    # When: the census scans the repository
    census = census_operator_g_evidence(tmp_path, contract=census_contract())
    # Then: malformed structured input still fails the census closed
    assert census.status is CensusStatus.INCOMPLETE
    assert census.substantiates_zero is False
    assert "malformed_structured_file" in {issue.reason for issue in census.issues}
