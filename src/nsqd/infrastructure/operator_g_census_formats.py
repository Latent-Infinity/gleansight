from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import PurePosixPath
from typing import assert_never

import yaml

from nsqd.domain.operator_g_types import StructuredValue
from nsqd.infrastructure.operator_g_structured_inputs import (
    NonStringMappingInput,
    StructuredInput,
    StructuredNestingLimitInput,
    UnsupportedStructuredInput,
    parse_structured_input,
)


@dataclass(frozen=True, slots=True)
class StructuredFormatError(Exception):
    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(frozen=True, slots=True)
class _NestingLimitError(Exception):
    depth: int

    def __str__(self) -> str:
        return f"structured nesting exceeds depth {self.depth}"


@dataclass(frozen=True, slots=True)
class _UnsupportedStructuredValueError(Exception):
    value_type: str

    def __str__(self) -> str:
        return f"unsupported structured value type: {self.value_type}"


@dataclass(frozen=True, slots=True)
class CalibrationFile:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class CalibrationCounts:
    root: str
    measurement_path: str
    study_path: str
    hash_path: str
    measurement_count: int
    study_count: int
    reconciled: bool


def derive_calibrations(
    files: Sequence[CalibrationFile], max_depth: int
) -> tuple[CalibrationCounts, ...]:
    grouped: dict[str, list[CalibrationFile]] = defaultdict(list)
    for file in files:
        parent = PurePosixPath(file.path).parent
        if parent.name.startswith("nsqd-tau-calibration-"):
            grouped[parent.as_posix()].append(file)
    return tuple(_derive_calibration(root, grouped[root], max_depth) for root in sorted(grouped))


def _derive_calibration(
    root: str, files: Sequence[CalibrationFile], max_depth: int
) -> CalibrationCounts:
    selected = {PurePosixPath(file.path).name: file for file in files}
    names = ("measurements.jsonl", "candidates.json", "candidate-hashes.json")
    measurement_path, study_path, hash_path = (f"{root}/{name}" for name in names)
    if not set(names).issubset(selected):
        return CalibrationCounts(root, measurement_path, study_path, hash_path, 0, 0, False)
    try:
        measurements = parse_documents(measurement_path, selected[names[0]].content, max_depth)
        candidate_docs = parse_documents(study_path, selected[names[1]].content, max_depth)
        hash_docs = parse_documents(hash_path, selected[names[2]].content, max_depth)
    except StructuredFormatError:
        return CalibrationCounts(root, measurement_path, study_path, hash_path, 0, 0, False)
    if len(candidate_docs) != 1 or len(hash_docs) != 1:
        return CalibrationCounts(
            root, measurement_path, study_path, hash_path, len(measurements), 0, False
        )
    candidate_root = candidate_docs[0]
    hash_root = hash_docs[0]
    studies = candidate_root.get("candidates") if isinstance(candidate_root, dict) else None
    if not isinstance(studies, list) or not isinstance(hash_root, dict):
        return CalibrationCounts(
            root, measurement_path, study_path, hash_path, len(measurements), 0, False
        )
    study_ids = _strings_from_mappings(studies, "id")
    indexed = [value for _, value in all_mappings(hash_root, "hashes") if "candidate_id" in value]
    indexed_ids = _strings_from_mappings(indexed, "candidate_id")
    measurement_pairs = _pairs(measurements)
    indexed_pairs = _pairs(indexed)
    packet_digest = hash_root.get("candidate_packet_sha256")
    reconciled = (
        len(study_ids) == len(set(study_ids))
        and len(indexed_ids) == len(set(indexed_ids))
        and set(study_ids) == set(indexed_ids)
        and len(measurement_pairs) == len(measurements)
        and len(indexed_pairs) == len(indexed)
        and len(measurement_pairs) == len(set(measurement_pairs))
        and set(measurement_pairs) == set(indexed_pairs)
        and packet_digest == selected[names[1]].sha256
    )
    return CalibrationCounts(
        root,
        measurement_path,
        study_path,
        hash_path,
        len(measurements),
        len(studies),
        reconciled,
    )


def _strings_from_mappings(values: Sequence[StructuredValue], field: str) -> list[str]:
    result: list[str] = []
    for value in values:
        selected = value.get(field) if isinstance(value, dict) else None
        if isinstance(selected, str):
            result.append(selected)
    return result


def _pairs(values: Sequence[StructuredValue]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        candidate_hash = value.get("candidate_artifact_hash")
        measurement_digest = value.get("measurement_artifact_digest")
        if isinstance(candidate_hash, str) and isinstance(measurement_digest, str):
            result.append((candidate_hash, measurement_digest))
    return result


def parse_documents(path: str, content: bytes, max_depth: int = 64) -> list[StructuredValue]:
    try:
        text = content.decode("utf-8")
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".jsonl":
            raw = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif suffix == ".json":
            raw = [json.loads(text)]
        elif suffix == ".toml":
            raw = [tomllib.loads(text)]
        else:
            raw = [yaml.safe_load(text)]
        return [
            _normalize(parse_structured_input(value, max_depth=max_depth), max_depth=max_depth)
            for value in raw
        ]
    except (
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        yaml.YAMLError,
        UnicodeDecodeError,
        RecursionError,
        _NestingLimitError,
        _UnsupportedStructuredValueError,
    ) as error:
        raise StructuredFormatError(path, str(error)) from error


def normalize[DecodedValue](
    value: DecodedValue, depth: int = 0, max_depth: int = 64
) -> StructuredValue:
    try:
        return _normalize(parse_structured_input(value, depth, max_depth), depth, max_depth)
    except (_NestingLimitError, _UnsupportedStructuredValueError, yaml.YAMLError) as error:
        raise StructuredFormatError("<value>", str(error)) from error


def _normalize(
    value: StructuredInput,
    depth: int = 0,
    max_depth: int = 64,
) -> StructuredValue:
    match value:
        case StructuredNestingLimitInput(depth=limit):
            raise _NestingLimitError(limit)
        case UnsupportedStructuredInput(value_type=value_type):
            raise _UnsupportedStructuredValueError(value_type)
        case NonStringMappingInput():
            raise yaml.YAMLError("non-string mapping key")
        case datetime() | date() | time():
            return value.isoformat()
        case None | str() | bool() | int() | float():
            return value
        case list() as items:
            return [_normalize(item, depth + 1, max_depth) for item in items]
        case dict() as mapping:
            return {key: _normalize(item, depth + 1, max_depth) for key, item in mapping.items()}
        case unreachable:
            assert_never(unreachable)


def record_candidates(
    value: StructuredValue, locator: str
) -> Iterator[tuple[str, dict[str, StructuredValue]]]:
    for nested_locator, mapping in all_mappings(value, locator):
        if (
            "failure_record_id" in mapping
            or mapping.get("record_type") == "approved_failed_experiment"
        ):
            yield nested_locator, mapping


def all_mappings(
    value: StructuredValue, locator: str
) -> Iterator[tuple[str, dict[str, StructuredValue]]]:
    match value:
        case dict() as mapping:
            yield locator, mapping
            for key in sorted(mapping):
                yield from all_mappings(mapping[key], f"{locator}/{key}")
        case list() as items:
            for index, item in enumerate(items):
                yield from all_mappings(item, f"{locator}/{index}")
        case None | str() | bool() | int() | float():
            return
        case unreachable:
            assert_never(unreachable)
