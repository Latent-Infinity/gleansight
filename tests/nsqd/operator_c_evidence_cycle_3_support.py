from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonMapping = dict[str, JsonValue]
type JsonPathElement = str | int


@dataclass(frozen=True, slots=True)
class MalformedPacketCase:
    name: str
    artifact: str
    path: tuple[JsonPathElement, ...]
    replacement: JsonValue


MALFORMED_PACKET_CASES: Final = (
    MalformedPacketCase(
        "wrong_records_type", "acquisition-receipts.json", ("records",), "not-a-list"
    ),
    MalformedPacketCase(
        "wrong_scalar_type", "acquisition-receipts.json", ("records", 0, "byte_count"), "2647744"
    ),
    MalformedPacketCase(
        "bool_integer_type", "acquisition-receipts.json", ("records", 0, "byte_count"), True
    ),
    MalformedPacketCase(
        "wrong_mapping_type", "acquisition-receipts.json", ("records", 0), "not-a-mapping"
    ),
    MalformedPacketCase(
        "duplicate_receipt_identity",
        "acquisition-receipts.json",
        ("records", 1, "receipt_id"),
        "arXiv:2602.04643v2#pdf",
    ),
    MalformedPacketCase(
        "duplicate_source_identity",
        "bibliographic-snapshot.json",
        ("records", 1, "source_id"),
        "arXiv:2602.04643v2",
    ),
    MalformedPacketCase(
        "duplicate_extract_identity", "source-extracts.jsonl", (1, "extract_id"), "SCJ-01"
    ),
    MalformedPacketCase("blank_quote", "source-extracts.jsonl", (0, "quote"), "   "),
    MalformedPacketCase(
        "blank_source_location", "source-extracts.jsonl", (0, "source_location"), "\t"
    ),
    MalformedPacketCase(
        "invalid_timestamp",
        "acquisition-receipts.json",
        ("records", 0, "retrieved_at_utc"),
        "not-a-timestamp",
    ),
    MalformedPacketCase(
        "non_utc_timestamp",
        "acquisition-receipts.json",
        ("records", 0, "retrieved_at_utc"),
        "2026-09-07T11:30:40+01:00",
    ),
    MalformedPacketCase(
        "wrong_reference_list_type", "claim-extractions.jsonl", (0, "factual_extract_ids"), "SCJ-01"
    ),
    MalformedPacketCase(
        "dangling_claim_extract",
        "claim-extractions.jsonl",
        (0, "factual_extract_ids"),
        ["MISSING-EXTRACT"],
    ),
    MalformedPacketCase(
        "dangling_prior_extract",
        "direct-a-to-c-prior-art.jsonl",
        (0, "evidence_extract_ids"),
        ["MISSING-EXTRACT"],
    ),
)


def _nonblank(value: str) -> str:
    assert value.strip()
    return value


def _utc_timestamp(value: str) -> str:
    assert value.endswith("Z")
    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() == timedelta(0)
    return value


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, strict=True)


class _Receipt(_StrictModel):
    receipt_id: str
    url: str
    sha256: str
    byte_count: int
    retrieved_at_utc: str

    _strings = field_validator("receipt_id", "url", "sha256")(_nonblank)
    _timestamp = field_validator("retrieved_at_utc")(_utc_timestamp)

    @model_validator(mode="after")
    def require_positive_byte_count(self) -> Self:
        assert type(self.byte_count) is int and self.byte_count > 0
        return self


class _Receipts(_StrictModel):
    cutoff_utc: str
    records: list[_Receipt]

    _cutoff = field_validator("cutoff_utc")(_utc_timestamp)

    @model_validator(mode="after")
    def require_unique_receipts(self) -> Self:
        identities = [record.receipt_id for record in self.records]
        assert len(identities) == len(set(identities))
        return self


class _Source(_StrictModel):
    source_id: str
    authors: list[str]
    full_text_inspected: bool
    published_at_utc: str | None = None
    updated_at_utc: str | None = None

    _source_id = field_validator("source_id")(_nonblank)

    @field_validator("authors")
    @classmethod
    def require_nonblank_authors(cls, values: list[str]) -> list[str]:
        assert values and all(value.strip() for value in values)
        return values

    @field_validator("published_at_utc", "updated_at_utc")
    @classmethod
    def require_utc_when_present(cls, value: str | None) -> str | None:
        return None if value is None else _utc_timestamp(value)


class _Snapshot(_StrictModel):
    cutoff_utc: str
    records: list[_Source]

    _cutoff = field_validator("cutoff_utc")(_utc_timestamp)

    @model_validator(mode="after")
    def require_unique_sources(self) -> Self:
        identities = [record.source_id for record in self.records]
        assert len(identities) == len(set(identities))
        return self


class _Extract(_StrictModel):
    extract_id: str
    receipt_id: str
    source_id: str
    source_sha256: str
    direction: str
    polarity: str
    quote: str
    source_location: str

    _strings = field_validator(
        "extract_id",
        "receipt_id",
        "source_id",
        "source_sha256",
        "direction",
        "polarity",
        "quote",
        "source_location",
    )(_nonblank)

    @model_validator(mode="after")
    def require_closed_values(self) -> Self:
        assert self.direction in {"A_to_B", "A_to_C", "B_to_C"}
        assert self.polarity in {"negative_result", "positive", "scope_limitation"}
        return self


class _Claim(_StrictModel):
    factual_extract_ids: list[str]


class _PriorArt(_StrictModel):
    evidence_extract_ids: list[str]


def _validate_model(model: type[BaseModel], payload: JsonMapping) -> None:
    model.model_validate(payload)


_JSON_VALIDATORS: Final[dict[str, Callable[[JsonMapping], None]]] = {
    "acquisition-receipts.json": lambda payload: _validate_model(_Receipts, payload),
    "bibliographic-snapshot.json": lambda payload: _validate_model(_Snapshot, payload),
}


def validate_json_document(name: str, payload: JsonMapping) -> None:
    validator = _JSON_VALIDATORS.get(name)
    if validator is None:
        return
    try:
        validator(payload)
    except ValidationError as error:
        raise AssertionError(f"invalid {name}") from error


def _extract_ids(root: Path) -> set[str]:
    rows: list[JsonValue] = [
        json.loads(line)
        for line in (root / "source-extracts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    extracts = [_Extract.model_validate(row) for row in rows]
    identities = [extract.extract_id for extract in extracts]
    assert len(identities) == len(set(identities))
    return set(identities)


def _validate_extracts(rows: list[JsonMapping], root: Path) -> None:
    del root
    extracts = [_Extract.model_validate(row) for row in rows]
    identities = [extract.extract_id for extract in extracts]
    assert len(identities) == len(set(identities))


def _validate_claims(rows: list[JsonMapping], root: Path) -> None:
    references = {
        reference for row in rows for reference in _Claim.model_validate(row).factual_extract_ids
    }
    assert references <= _extract_ids(root)


def _validate_prior_art(rows: list[JsonMapping], root: Path) -> None:
    references = {
        reference
        for row in rows
        for reference in _PriorArt.model_validate(row).evidence_extract_ids
    }
    assert references <= _extract_ids(root)


_JSONL_VALIDATORS: Final[dict[str, Callable[[list[JsonMapping], Path], None]]] = {
    "source-extracts.jsonl": _validate_extracts,
    "claim-extractions.jsonl": _validate_claims,
    "direct-a-to-c-prior-art.jsonl": _validate_prior_art,
}


def validate_jsonl_document(name: str, rows: list[JsonMapping], root: Path) -> None:
    validator = _JSONL_VALIDATORS.get(name)
    if validator is None:
        return
    try:
        validator(rows, root)
    except ValidationError as error:
        raise AssertionError(f"invalid {name}") from error


def _set_value(
    payload: JsonValue, path: tuple[JsonPathElement, ...], replacement: JsonValue
) -> None:
    current = payload
    for element in path[:-1]:
        match current, element:
            case dict() as mapping, str() as key:
                current = mapping[key]
            case list() as sequence, int() as index:
                current = sequence[index]
            case _:
                raise AssertionError
    final = path[-1]
    match current, final:
        case dict() as mapping, str() as key:
            mapping[key] = replacement
        case list() as sequence, int() as index:
            sequence[index] = replacement
        case _:
            raise AssertionError


def tamper_packet(root: Path, case: MalformedPacketCase) -> None:
    path = root / case.artifact
    if path.suffix == ".jsonl":
        payload: JsonValue = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    _set_value(payload, case.path, case.replacement)
    if path.suffix == ".jsonl":
        assert isinstance(payload, list)
        path.write_text("\n".join(json.dumps(row) for row in payload) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
