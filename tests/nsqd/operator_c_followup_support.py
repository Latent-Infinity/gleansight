from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

MANIFEST_KEYS: Final = {"artifact_sha256", "packet_digest", "schema_version"}
MANIFEST_ARTIFACT_NAMES: Final = {
    "README.md",
    "acquisition-receipts.json",
    "bibliographic-query-receipts.json",
    "evidence-ledger.json",
    "source-extracts.jsonl",
}


def _json(path: Path) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), "followup.document.mapping"
    return payload


def _jsonl(path: Path) -> list[dict[str, JsonValue]]:
    payloads: list[JsonValue] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert payloads and all(isinstance(payload, dict) for payload in payloads), (
        "followup.document.nonempty_jsonl_mappings"
    )
    return [payload for payload in payloads if isinstance(payload, dict)]


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict), "followup.value.mapping"
    return value


def _mappings(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list), "followup.value.mapping_list"
    return [_mapping(item) for item in value]


def _string(value: JsonValue) -> str:
    assert isinstance(value, str) and value.strip(), "followup.value.nonblank_string"
    return value


def _strings(value: JsonValue) -> set[str]:
    assert isinstance(value, list), "followup.value.unique_string_list"
    strings = [_string(item) for item in value]
    assert len(strings) == len(set(strings)), "followup.value.unique_string_list"
    return set(strings)


def validate_followup_semantics(root: Path) -> None:
    receipts = _json(root / "acquisition-receipts.json")
    receipt_rows = _mappings(receipts["records"])
    receipt_ids = [_string(row["receipt_id"]) for row in receipt_rows]
    assert len(receipt_ids) == len(set(receipt_ids)), "followup.receipt.id.unique"
    for row in receipt_rows:
        assert row["http_status"] == 200, "followup.receipt.http_status.ok"
        assert type(row["byte_count"]) is int and row["byte_count"] > 0, (
            "followup.receipt.byte_count.positive_integer"
        )
        assert len(_string(row["sha256"])) == 64, "followup.receipt.sha256.length"
        assert _string(row["retrieved_at_utc"]).endswith("Z"), (
            "followup.receipt.retrieved_at_utc.utc"
        )

    receipt_digests = {_string(row["receipt_id"]): _string(row["sha256"]) for row in receipt_rows}
    extracts = _jsonl(root / "source-extracts.jsonl")
    extract_ids = [_string(row["extract_id"]) for row in extracts]
    assert len(extract_ids) == len(set(extract_ids)), "followup.extract.id.unique"
    for row in extracts:
        receipt_id = _string(row["receipt_id"])
        assert receipt_id in receipt_digests, "followup.extract.receipt_id.known"
        quote = _string(row["quote"])
        assert row["source_sha256"] == receipt_digests[receipt_id], (
            "followup.extract.source_sha256.receipt_match"
        )
        assert row["quote_sha256"] == hashlib.sha256(quote.encode()).hexdigest(), (
            "followup.extract.quote_sha256.match"
        )
        assert type(row["pdf_page"]) is int or row["pdf_page"] is None, (
            "followup.extract.pdf_page.integer_or_null"
        )
        assert _string(row["source_location"]), "followup.extract.source_location.nonblank"

    queries = _json(root / "bibliographic-query-receipts.json")
    query_rows = _mappings(queries["records"])
    assert {_string(row["provider"]) for row in query_rows} == {
        "arXiv",
        "Crossref",
        "OpenAlex",
    }, "followup.bibliographic.providers.exact"
    for row in query_rows:
        assert row["http_status"] == 200, "followup.bibliographic.http_status.ok"
        assert type(row["response_byte_count"]) is int and row["response_byte_count"] > 0, (
            "followup.bibliographic.response_byte_count.positive_integer"
        )
        assert len(_string(row["response_sha256"])) == 64, (
            "followup.bibliographic.response_sha256.length"
        )
        assert type(row["returned_count"]) is int and row["returned_count"] >= 0, (
            "followup.bibliographic.returned_count.nonnegative_integer"
        )
        assert type(row["page_size"]) is int and row["page_size"] > 0, (
            "followup.bibliographic.page_size.positive_integer"
        )
        assert _string(row["queried_at_utc"]).endswith("Z"), (
            "followup.bibliographic.queried_at_utc.utc"
        )

    ledger = _json(root / "evidence-ledger.json")
    interactions = _mappings(ledger["interaction_checks"])
    query_ids = {_string(row["query_id"]) for row in query_rows}
    assert all(_strings(row["query_receipt_ids"]) <= query_ids for row in interactions), (
        "followup.ledger.query_receipt_ids.known"
    )
    assert all(row["status"] == "not_observed_within_bounded_queries" for row in interactions), (
        "followup.ledger.interaction_status.bounded_absence"
    )
    assert ledger["authorization_state"] == "report_only", (
        "followup.ledger.authorization_state.report_only"
    )
    assert ledger["candidate_combinations"] == [], "followup.ledger.candidate_combinations.empty"
    assert ledger["candidate_outputs"] == [], "followup.ledger.candidate_outputs.empty"
    assert ledger["evidence_sufficient"] is False, "followup.ledger.evidence_sufficient.false"
    assert ledger["human_acceptance"] == "not_requested", (
        "followup.ledger.human_acceptance.not_requested"
    )
    assert ledger["runtime_authorized"] is False, "followup.ledger.runtime_authorized.false"
    assert ledger["operator_c_status"] == "blocked", "followup.ledger.operator_c.blocked"
    assert ledger["operator_d_status"] == "blocked", "followup.ledger.operator_d.blocked"


def validate_followup_manifest(root: Path) -> None:
    manifest = _json(root / "packet-manifest.json")
    assert set(manifest) == MANIFEST_KEYS, "followup.manifest.keys.exact"
    assert manifest["schema_version"] == 1, "followup.manifest.schema_version.one"
    artifact_digests = _mapping(manifest["artifact_sha256"])
    assert set(artifact_digests) == MANIFEST_ARTIFACT_NAMES, "followup.manifest.artifact_keys.exact"
    for name, expected_digest in artifact_digests.items():
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        assert digest == expected_digest, f"followup.manifest.artifact_sha256.match:{name}"
    preimage = json.dumps(artifact_digests, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest(), (
        "followup.manifest.packet_digest.match"
    )


def validate_followup_packet(root: Path) -> None:
    validate_followup_semantics(root)
    validate_followup_manifest(root)
