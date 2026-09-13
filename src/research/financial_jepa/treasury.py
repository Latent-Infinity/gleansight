from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
import xml.etree.ElementTree as et
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict

from research.financial_jepa.contracts import (
    TENOR_FIELDS,
    Deadline,
    ExperimentConfig,
    ParsedYieldRows,
    ProtocolError,
    YieldRow,
)

URL_TEMPLATE: Final = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)
MAX_YEAR_BYTES: Final = 8_000_000


class CacheMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int
    url: str
    retrieved_at_utc: str
    status_code: int
    content_type: str
    etag: str | None
    last_modified: str | None
    sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class AcquisitionReceipt:
    files: tuple[Path, ...]
    metadata: tuple[CacheMetadata, ...]


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    config: ExperimentConfig
    data_dir: Path
    offline: bool
    deadline: Deadline
    transport: httpx.BaseTransport | None = None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_year_xml(payload: bytes, expected_year: int) -> ParsedYieldRows:
    if not payload.strip():
        raise ProtocolError("Treasury response is empty")
    try:
        root = et.fromstring(payload)
    except et.ParseError as exc:
        raise ProtocolError("Treasury response is malformed XML") from exc
    if any(
        _local_name(element.tag) == "link" and element.attrib.get("rel") == "next"
        for element in root.iter()
    ):
        raise ProtocolError(f"Treasury response for {expected_year} advertises continuation")
    rows: list[YieldRow] = []
    dropped: list[date] = []
    missing_records: list[tuple[date, tuple[str, ...]]] = []
    seen: set[date] = set()
    for entry in (element for element in root.iter() if _local_name(element.tag) == "entry"):
        fields = {
            _local_name(element.tag): (element.text or "").strip()
            for element in entry.iter()
            if element is not entry
        }
        raw_date = fields.get("NEW_DATE") or fields.get("Date")
        if raw_date is None:
            raise ProtocolError("Treasury row has no date")
        try:
            observed_on = date.fromisoformat(raw_date[:10])
        except ValueError as exc:
            raise ProtocolError(f"invalid Treasury date: {raw_date}") from exc
        if observed_on.year != expected_year:
            raise ProtocolError(f"Treasury row year does not match {expected_year}")
        if observed_on in seen:
            raise ProtocolError(f"duplicate Treasury date: {observed_on.isoformat()}")
        seen.add(observed_on)
        missing_fields = tuple(field for field in TENOR_FIELDS if not fields.get(field))
        if missing_fields:
            dropped.append(observed_on)
            missing_records.append((observed_on, missing_fields))
            continue
        try:
            values = (
                float(fields[TENOR_FIELDS[0]]),
                float(fields[TENOR_FIELDS[1]]),
                float(fields[TENOR_FIELDS[2]]),
                float(fields[TENOR_FIELDS[3]]),
                float(fields[TENOR_FIELDS[4]]),
                float(fields[TENOR_FIELDS[5]]),
                float(fields[TENOR_FIELDS[6]]),
                float(fields[TENOR_FIELDS[7]]),
            )
        except ValueError as exc:
            raise ProtocolError(f"malformed Treasury yield on {observed_on.isoformat()}") from exc
        if any(not math.isfinite(value) for value in values):
            raise ProtocolError(f"nonfinite Treasury yield on {observed_on.isoformat()}")
        rows.append(YieldRow(observed_on, values, False))
    if not rows:
        raise ProtocolError(f"Treasury response for {expected_year} has no complete rows")
    return ParsedYieldRows(
        _apply_missing_boundaries(rows, dropped),
        tuple(sorted(dropped)),
        tuple(sorted(missing_records)),
    )


def _apply_missing_boundaries(rows: list[YieldRow], dropped: list[date]) -> tuple[YieldRow, ...]:
    ordered = sorted(rows, key=lambda row: row.observed_on)
    missing = sorted(dropped)
    bounded: list[YieldRow] = []
    previous: date | None = None
    for row in ordered:
        boundary = row.boundary_before
        if previous is not None and any(previous < day < row.observed_on for day in missing):
            boundary = True
        bounded.append(YieldRow(row.observed_on, row.yields, boundary))
        previous = row.observed_on
    return tuple(bounded)


def parse_years(paths: tuple[Path, ...]) -> ParsedYieldRows:
    rows: list[YieldRow] = []
    dropped: list[date] = []
    missing_records: list[tuple[date, tuple[str, ...]]] = []
    for path in paths:
        try:
            year = int(path.stem)
        except ValueError as exc:
            raise ProtocolError(f"cache filename is not a year: {path.name}") from exc
        parsed = parse_year_xml(path.read_bytes(), year)
        rows.extend(parsed.rows)
        dropped.extend(parsed.dropped_missing_dates)
        missing_records.extend(parsed.missing_fields_by_date)
    dates = [row.observed_on for row in rows]
    if len(dates) != len(set(dates)):
        raise ProtocolError("duplicate Treasury dates across yearly files")
    return ParsedYieldRows(
        _apply_missing_boundaries(rows, dropped),
        tuple(sorted(dropped)),
        tuple(sorted(missing_records)),
    )


def _metadata_path(data_dir: Path, year: int) -> Path:
    return data_dir / f"{year}.metadata.json"


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _verified_cached(data_dir: Path, year: int) -> tuple[Path, CacheMetadata]:
    content_path = data_dir / f"{year}.xml"
    metadata_path = _metadata_path(data_dir, year)
    if not content_path.is_file() or not metadata_path.is_file():
        raise ProtocolError(f"offline Treasury cache is incomplete for {year}")
    try:
        metadata = CacheMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ProtocolError(f"invalid Treasury cache metadata for {year}") from exc
    content = content_path.read_bytes()
    if metadata.year != year or metadata.sha256 != hashlib.sha256(content).hexdigest():
        raise ProtocolError(f"Treasury cache hash mismatch for {year}")
    if metadata.byte_count != len(content):
        raise ProtocolError(f"Treasury cache byte count mismatch for {year}")
    parse_year_xml(content, year)
    return content_path, metadata


def acquire_years(request: AcquisitionRequest) -> AcquisitionReceipt:
    request.deadline.check()
    request.data_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    metadata_rows: list[CacheMetadata] = []
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    for year in request.config.years:
        request.deadline.check()
        if request.offline:
            content_path, metadata = _verified_cached(request.data_dir, year)
        else:
            url = URL_TEMPLATE.format(year=year)
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                transport=request.transport,
            ) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        request.deadline.check()
                        size += len(chunk)
                        if size > MAX_YEAR_BYTES:
                            raise ProtocolError(f"Treasury response exceeds byte limit for {year}")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    parse_year_xml(content, year)
                    metadata = CacheMetadata(
                        year=year,
                        url=str(response.url),
                        retrieved_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type", ""),
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                        sha256=hashlib.sha256(content).hexdigest(),
                        byte_count=len(content),
                    )
            content_path = request.data_dir / f"{year}.xml"
            _write_atomic(content_path, content)
            _write_atomic(
                _metadata_path(request.data_dir, year),
                (
                    json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
                ).encode(),
            )
        files.append(content_path)
        metadata_rows.append(metadata)
    return AcquisitionReceipt(tuple(files), tuple(metadata_rows))
