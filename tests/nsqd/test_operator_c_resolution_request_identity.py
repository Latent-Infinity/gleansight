from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from tests.nsqd.operator_c_resolution_contracts import EXPECTED_QUERY_URLS
from tests.nsqd.operator_c_resolution_support import validate_resolution_semantics

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PACKET_ROOT: Final = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-resolution-2026-09-09"
)
PROTOCOL_CUTOFF: Final = "2026-09-09T15:11:38Z"
QUERY_COMPLETION: Final = "2026-09-09T20:27:38Z"


def _json(path: Path) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _query_rows() -> list[dict[str, JsonValue]]:
    packet = _json(PACKET_ROOT / "bibliographic-query-receipts.json")
    batches = packet["query_batches"]
    assert isinstance(batches, list)
    rows: list[dict[str, JsonValue]] = []
    for batch in batches:
        assert isinstance(batch, dict)
        records = batch["records"]
        assert isinstance(records, list)
        assert all(isinstance(record, dict) for record in records)
        rows.extend(record for record in records if isinstance(record, dict))
    return rows


def test_resolution_cutoff_is_frozen_separately_from_completion() -> None:
    # Given a packet governed by the frozen protocol cutoff
    receipts = _json(PACKET_ROOT / "acquisition-receipts.json")
    readme = (PACKET_ROOT / "README.md").read_text(encoding="utf-8")
    # When cutoff and completion timestamps are read back
    validate_resolution_semantics(PACKET_ROOT)
    # Then the protocol cutoff is exact and query completion is labeled separately
    assert receipts["cutoff_utc"] == PROTOCOL_CUTOFF
    assert f"**Protocol cutoff:** `{PROTOCOL_CUTOFF}`" in readme
    assert f"**Latest query completion:** `{QUERY_COMPLETION}`" in readme


def test_resolution_query_receipts_bind_exact_executed_request_urls() -> None:
    # Given response hashes produced by thirteen frozen requests
    rows = _query_rows()
    by_id = {row["query_id"]: row for row in rows}
    # When request and effective URL identities are read back
    actual = {query_id: (row["retrieval_uri"], row["final_url"]) for query_id, row in by_id.items()}
    expected = {
        query_id: urls if isinstance(urls, tuple) else (urls, urls)
        for query_id, urls in EXPECTED_QUERY_URLS.items()
    }
    # Then every response is bound to the exact request form that produced it
    assert actual == expected
    assert all("request_uri_state" not in row for row in rows)
