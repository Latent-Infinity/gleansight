from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest

from research.financial_jepa.contracts import Deadline, ExperimentConfig, ProtocolError, YieldRow
from research.financial_jepa.dataset import prepare_splits
from research.financial_jepa.provenance import rights_metadata
from research.financial_jepa.treasury import (
    AcquisitionRequest,
    CacheMetadata,
    acquire_years,
    parse_year_xml,
    parse_years,
)
from tests.research.support import curve


def _xml(rows: list[str]) -> bytes:
    return (
        '<?xml version="1.0"?><feed '
        'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
        'xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"><entry><content><m:properties>'
        + "</m:properties></content></entry><entry><content><m:properties>".join(rows)
        + "</m:properties></content></entry></feed>"
    ).encode()


def _row(day: str, *, omit: str = "", include_date: bool = True) -> str:
    fields = [
        ("BC_10YEAR", "4.8"),
        ("BC_3MONTH", "4.1"),
        ("BC_2YEAR", "4.4"),
        ("BC_6MONTH", "4.2"),
        ("BC_1YEAR", "4.3"),
        ("BC_3YEAR", "4.5"),
        ("BC_5YEAR", "4.6"),
        ("BC_7YEAR", "4.7"),
    ]
    values = "".join(f"<d:{name}>{value}</d:{name}>" for name, value in fields if name != omit)
    date_field = f"<d:NEW_DATE>{day}T00:00:00</d:NEW_DATE>" if include_date else ""
    return f"{date_field}{values}"


def _rows(start: date, count: int, base: float) -> tuple[YieldRow, ...]:
    return tuple(
        YieldRow(
            observed_on=start + timedelta(days=index),
            yields=curve(base + index * 0.01, 0.1),
            boundary_before=False,
        )
        for index in range(count)
    )


def test_parser_is_field_order_independent_and_missing_row_is_boundary() -> None:
    parsed = parse_year_xml(
        _xml(
            [
                _row("2020-01-06"),
                _row("2020-01-03", omit="BC_5YEAR"),
                _row("2020-01-02"),
            ]
        ),
        2020,
    )

    assert parsed.rows[0].yields == (4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8)
    assert parsed.rows[1].boundary_before is True
    assert parsed.dropped_missing_dates == (date(2020, 1, 3),)


@pytest.mark.parametrize(
    "payload",
    [
        _xml([_row("2020-01-02"), _row("2020-01-02")]),
        _xml([_row("not-a-date")]),
        _xml([_row("2020-01-02").replace("4.8", "nan")]),
        b"<feed />",
    ],
)
def test_parser_rejects_duplicate_invalid_nonfinite_and_empty(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_year_xml(payload, 2020)


def test_prepare_splits_keeps_windows_inside_segments_and_uses_train_scaler() -> None:
    config = ExperimentConfig.synthetic(context_length=3, future_length=2, batch_size=2, epochs=1)
    train = _rows(date(2017, 12, 20), 12, 1.0)
    validation = _rows(date(2018, 1, 1), 12, 20.0)
    test = _rows(date(2022, 1, 1), 12, 40.0)

    prepared = prepare_splits(train + validation + test, config)

    expected = np.asarray([row.yields for row in train], dtype=np.float64).mean(axis=0)
    assert np.allclose(prepared.scaler.mean, expected)
    assert all(window.origin_date.year == 2017 for window in prepared.train.windows)
    assert all(window.origin_date.year == 2018 for window in prepared.validation.windows)
    assert all(window.origin_date.year == 2022 for window in prepared.test.windows)


def test_prepare_splits_rejects_zero_standard_deviation_raw_training_rows() -> None:
    constant = curve(1.0, 0.1)
    rows = tuple(
        YieldRow(date(year, 1, 1) + timedelta(days=index), constant, False)
        for year in (2017, 2018, 2022)
        for index in range(6)
    )
    config = ExperimentConfig.synthetic(context_length=2, future_length=1, batch_size=2, epochs=1)

    with pytest.raises(ProtocolError, match="zero standard deviation"):
        prepare_splits(rows, config)


def test_methodology_date_and_large_gap_create_hard_boundaries() -> None:
    config = ExperimentConfig.synthetic(context_length=2, future_length=1, batch_size=2, epochs=1)
    rows = _rows(date(2018, 1, 1), 5, 1.0) + _rows(date(2018, 1, 10), 5, 2.0)
    methodology = _rows(date(2021, 12, 3), 2, 3.0) + _rows(date(2021, 12, 6), 3, 4.0)
    train = _rows(date(2017, 1, 1), 5, 0.0)
    test = _rows(date(2022, 1, 1), 5, 5.0)

    prepared = prepare_splits(train + rows + methodology + test, config)

    assert prepared.validation.segment_count == 4
    assert all(
        not (window.context_dates[0] < date(2021, 12, 6) <= window.target_dates[-1])
        for window in prepared.validation.windows
    )


def test_data_and_output_paths_reject_protected_repository_trees(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    config = ExperimentConfig.canonical()

    with pytest.raises(ProtocolError):
        config.validate_paths(repo_root, repo_root / "data", tmp_path / "run")
    with pytest.raises(ProtocolError):
        config.validate_paths(repo_root, tmp_path / "source", repo_root / "docs" / "run")


def test_offline_cache_verifies_recorded_byte_hash(tmp_path: Path) -> None:
    config = ExperimentConfig.synthetic(
        context_length=2, future_length=1, batch_size=2, epochs=1
    ).model_copy(update={"years": (2020,)})
    payload = _xml([_row("2020-01-02")])
    content_path = tmp_path / "2020.xml"
    content_path.write_bytes(payload)
    metadata = CacheMetadata(
        year=2020,
        url="https://home.treasury.gov/example",
        retrieved_at_utc="2026-09-13T00:00:00Z",
        status_code=200,
        content_type="application/xml",
        etag=None,
        last_modified=None,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
    )
    (tmp_path / "2020.metadata.json").write_text(
        json.dumps(metadata.model_dump(mode="json")), encoding="utf-8"
    )

    receipt = acquire_years(AcquisitionRequest(config, tmp_path, True, Deadline.start(10.0)))
    content_path.write_bytes(payload + b" ")

    assert receipt.files == (content_path,)
    with pytest.raises(ProtocolError, match="hash mismatch"):
        acquire_years(AcquisitionRequest(config, tmp_path, True, Deadline.start(10.0)))


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"<broken", "malformed XML"),
        (_xml([_row("2021-01-02")]), "does not match"),
        (_xml([_row("2020-01-02").replace("4.8", "oops")]), "malformed Treasury yield"),
        (_xml([_row("2020-01-02", include_date=False)]), "no date"),
    ],
)
def test_parser_reports_typed_boundary_errors(payload: bytes, message: str) -> None:
    with pytest.raises(ProtocolError, match=message):
        parse_year_xml(payload, 2020)


def test_parse_years_rejects_non_year_filename(tmp_path: Path) -> None:
    path = tmp_path / "treasury.xml"
    path.write_bytes(_xml([_row("2020-01-02")]))

    with pytest.raises(ProtocolError, match="filename"):
        parse_years((path,))


def test_online_acquisition_streams_official_url_and_records_metadata(tmp_path: Path) -> None:
    config = ExperimentConfig.synthetic(
        context_length=2, future_length=1, batch_size=2, epochs=1
    ).model_copy(update={"years": (2020,)})
    payload = _xml([_row("2020-01-02")])
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "application/xml", "etag": "example"},
        )

    receipt = acquire_years(
        AcquisitionRequest(
            config,
            tmp_path,
            False,
            Deadline.start(10.0),
            httpx.MockTransport(handler),
        )
    )

    assert requested == [
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        "?data=daily_treasury_yield_curve&field_tdr_date_value=2020"
    ]
    assert receipt.metadata[0].sha256 == hashlib.sha256(payload).hexdigest()
    assert receipt.metadata[0].etag == "example"
    assert rights_metadata()["license_expression"] == "NOASSERTION"


def test_online_acquisition_rejects_partial_year_feed_with_next_link(tmp_path: Path) -> None:
    config = ExperimentConfig.synthetic(
        context_length=2, future_length=1, batch_size=2, epochs=1
    ).model_copy(update={"years": (2020,)})
    payload = _xml([_row("2020-01-02")]).replace(
        b"</feed>",
        b'<link rel="next" href="https://home.treasury.gov/page-2" /></feed>',
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, request=request)

    with pytest.raises(ProtocolError, match="continuation"):
        acquire_years(
            AcquisitionRequest(
                config,
                tmp_path,
                False,
                Deadline.start(10.0),
                httpx.MockTransport(handler),
            )
        )

    assert not (tmp_path / "2020.xml").exists()
