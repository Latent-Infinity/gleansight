from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from tests.nsqd.operator_c_resolution_contracts import (
    BATCH_CONTRACTS,
    EXPECTED_QUERY_URLS,
    EXTRACT_BINDINGS,
    EXTRACT_LOCATIONS,
    EXTRACT_QUOTE_SHA256,
    PROTOCOL_PATH,
)
from tests.nsqd.operator_c_resolution_data import (
    QUERY_RESPONSES,
    SOURCE_IMPORTS,
    validate_ledger,
    validate_relations,
)
from tests.nsqd.operator_c_resolution_review_contracts import EVIDENCE_ARTIFACTS

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonMapping = dict[str, JsonValue]
type ReceiptIdentity = tuple[str, str, str]

ARTIFACT_NAMES: Final = {
    *EVIDENCE_ARTIFACTS,
    "packet-manifest.json",
    "review-summary.json",
    "review-seal.json",
}

PROTOCOL_DIGEST: Final = "460986b339301e9012d56d34e5dca93bcfa30493d23b60317b9e992f9a5dc69c"
PROTOCOL_SHA256: Final = "e1a800081299c89a39fda4f1f0cab08260e888add305d2609163051ad437f742"
PROTOCOL_CUTOFF: Final = "2026-09-09T15:11:38Z"
RETENTION_KEYS: Final = {
    "artifact_identity",
    "state",
    "content_sha256_or_null",
    "byte_count_or_null",
    "repository_path_or_null",
    "authorized_external_locator_or_null",
    "reason",
    "recorded_at_utc",
}


def _json(path: Path) -> JsonMapping:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"resolution.document.mapping:{path.name}"
    return payload


def _jsonl(path: Path) -> list[JsonMapping]:
    payloads: list[JsonValue] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert payloads and all(isinstance(payload, dict) for payload in payloads), (
        "resolution.document.nonempty_jsonl_mappings"
    )
    return [payload for payload in payloads if isinstance(payload, dict)]


def _mapping(value: JsonValue) -> JsonMapping:
    assert isinstance(value, dict), "resolution.value.mapping"
    return value


def _mappings(value: JsonValue) -> list[JsonMapping]:
    assert isinstance(value, list), "resolution.value.mapping_list"
    return [_mapping(item) for item in value]


def _string(value: JsonValue) -> str:
    assert isinstance(value, str) and value.strip(), "resolution.value.nonblank_string"
    return value


def _validate_retention(value: JsonValue, expected_state: str) -> JsonMapping:
    retention = _mapping(value)
    assert set(retention) == RETENTION_KEYS, "resolution.retention.fields.exact"
    assert retention["state"] == expected_state, "resolution.retention.state.match"
    assert retention["repository_path_or_null"] is None, "resolution.retention.repository_path.null"
    assert retention["authorized_external_locator_or_null"] is None, (
        "resolution.retention.external_locator.null"
    )
    _string(retention["reason"])
    assert _string(retention["recorded_at_utc"]).endswith("Z"), (
        "resolution.retention.recorded_at.utc"
    )
    return retention


def validate_acquisition(root: Path) -> dict[str, ReceiptIdentity]:
    packet = _json(root / "acquisition-receipts.json")
    assert packet["protocol_path"] == PROTOCOL_PATH, "resolution.protocol.path.frozen"
    assert packet["protocol_packet_digest"] == PROTOCOL_DIGEST, "resolution.protocol.digest.frozen"
    assert packet["protocol_sha256"] == PROTOCOL_SHA256, "resolution.protocol.sha256.frozen"
    assert packet["cutoff_utc"] == PROTOCOL_CUTOFF, "resolution.protocol.cutoff.frozen"
    rows = _mappings(packet["records"])
    identities = [_string(row["stable_source_id"]) for row in rows]
    assert len(rows) == 3, "resolution.acquisition.source_count.three"
    assert len(identities) == len(set(identities)), "resolution.acquisition.identity.unique"
    receipts: dict[str, ReceiptIdentity] = {}
    for row in rows:
        stable_id = _string(row["stable_source_id"])
        assert stable_id in SOURCE_IMPORTS, "resolution.acquisition.source.known"
        version, url, byte_count, digest = SOURCE_IMPORTS[stable_id]
        actual = (
            row["version_id"],
            row["retrieval_uri"],
            row["byte_count"],
            row["content_sha256"],
        )
        assert actual == (
            version,
            url,
            byte_count,
            digest,
        ), "resolution.acquisition.source.exact"
        assert row["http_status"] == 200, "resolution.acquisition.http_status.ok"
        assert row["media_type"] == "application/pdf", "resolution.acquisition.media_type.pdf"
        assert row["retrieval_uri"] == row["final_url"], "resolution.acquisition.url.exact"
        retention = _validate_retention(row["retention"], "not_retained_repository_policy")
        assert (retention["content_sha256_or_null"], retention["byte_count_or_null"]) == (
            digest,
            byte_count,
        ), "resolution.retention.content_binding.match"
        receipts[_string(row["receipt_id"])] = (stable_id, version, digest)
    return receipts


def validate_extracts(root: Path, receipts: dict[str, ReceiptIdentity]) -> dict[str, JsonMapping]:
    rows = _jsonl(root / "source-extracts.jsonl")
    by_id = {_string(row["extract_id"]): row for row in rows}
    assert set(by_id) == set(EXTRACT_BINDINGS), "resolution.extract.identity.exact"
    for extract_id, row in by_id.items():
        receipt_id = _string(row["receipt_id"])
        assert receipt_id in receipts, "resolution.extract.receipt.known"
        stable_id, version, digest = receipts[receipt_id]
        assert row["stable_source_id"] == stable_id, "resolution.extract.stable_source_id.match"
        assert row["version_id"] == version, "resolution.extract.version_id.match"
        assert row["source_sha256"] == digest, "resolution.extract.receipt_digest.match"
        quote = _string(row["quote"])
        assert row["quote_sha256"] == hashlib.sha256(quote.encode()).hexdigest(), (
            "resolution.extract.quote_sha256.match"
        )
        assert row["quote_sha256"] == EXTRACT_QUOTE_SHA256[extract_id], (
            "resolution.extract.quote.exact"
        )
        expected_stable, expected_version, expected_page = EXTRACT_BINDINGS[extract_id]
        assert (stable_id, version, row["pdf_page"]) == (
            expected_stable,
            expected_version,
            expected_page,
        ), "resolution.extract.location.exact"
        expected_page, expected_section, expected_location, has_printed_page = EXTRACT_LOCATIONS[
            extract_id
        ]
        assert row["pdf_page"] == expected_page, "resolution.extract.location.exact"
        assert row["section"] == expected_section, "resolution.extract.section.exact"
        assert row["source_location"] == expected_location, (
            "resolution.extract.source_location.exact"
        )
        assert ("printed_page" in row) is has_printed_page, (
            "resolution.extract.printed_page.presence"
        )
        if has_printed_page:
            assert row["printed_page"] is None, "resolution.extract.printed_page.unavailable"
    return by_id


def validate_queries(root: Path) -> set[str]:
    packet = _json(root / "bibliographic-query-receipts.json")
    assert packet["protocol_packet_digest"] == PROTOCOL_DIGEST, "resolution.protocol.digest.frozen"
    assert packet["cutoff_utc"] == PROTOCOL_CUTOFF, "resolution.protocol.cutoff.frozen"
    assert packet["maximum_query_batches"] == 3, "resolution.query.budget.frozen"
    assert packet["maximum_candidates_per_batch"] == 25, "resolution.query.result_budget.frozen"
    batches = _mappings(packet["query_batches"])
    assert [batch["batch_number"] for batch in batches] == [1, 2, 3], (
        "resolution.query.batches.exact"
    )
    for batch, (purpose, control, expected_query_ids) in zip(batches, BATCH_CONTRACTS, strict=True):
        actual_control = batch.get("control")
        actual_query_ids = tuple(_string(row["query_id"]) for row in _mappings(batch["records"]))
        assert (batch["purpose"], actual_control, actual_query_ids) == (
            purpose,
            control,
            expected_query_ids,
        ), "resolution.query.batch_identity.exact"
    derivation = _mapping(batches[2]["derivation"])
    assert derivation["status"] == "unavailable_nonreproducible", (
        "resolution.query.shuffled_derivation.unavailable"
    )
    assert all(
        derivation[field] is None
        for field in ("seed_material", "candidate_pool", "algorithm", "ordering_or_permutation")
    ), "resolution.query.shuffled_derivation.no_fabrication"
    assert derivation["declared_seed_sha256"] == batches[2]["seed_sha256"], (
        "resolution.query.shuffled_seed.bound"
    )
    rows = [row for batch in batches for row in _mappings(batch["records"])]
    query_ids = [_string(row["query_id"]) for row in rows]
    assert set(query_ids) == set(QUERY_RESPONSES), "resolution.query.identity.exact"
    assert len(query_ids) == len(set(query_ids)), "resolution.query.identity.unique"
    for row in rows:
        query_id = _string(row["query_id"])
        expected = QUERY_RESPONSES[query_id]
        expected_urls = EXPECTED_QUERY_URLS[query_id]
        if isinstance(expected_urls, tuple):
            expected_retrieval_uri, expected_final_url = expected_urls
        else:
            expected_retrieval_uri = expected_urls
            expected_final_url = expected_urls
        assert row["retrieval_uri"] == expected_retrieval_uri, "resolution.query.request_uri.exact"
        assert row["final_url"] == expected_final_url, "resolution.query.final_url.exact"
        actual = (
            row["http_status"],
            row["response_byte_count"],
            row["response_sha256"],
            row["returned_count"],
        )
        assert actual == expected, "resolution.query.response.exact"
        match row["http_status"]:
            case 200:
                identity = query_id == "arxiv-source-identity"
                expected_state = (
                    "source_identity_observed"
                    if identity
                    else "not_observed_within_bounded_queries"
                )
                assert row["observation_state"] == expected_state, (
                    "resolution.query.success.bounded_absence"
                )
                _validate_retention(row["retention"], "not_retained_repository_policy")
            case 429:
                assert row["observation_state"] == "unavailable_from_service", (
                    "resolution.query.unavailable.not_absence"
                )
                _validate_retention(row["retention"], "unavailable_from_service")
            case unexpected:
                raise AssertionError(f"resolution.query.http_status.allowed:{unexpected}")
    return set(query_ids)


def validate_resolution_semantics(root: Path) -> None:
    receipts = validate_acquisition(root)
    extracts = validate_extracts(root, receipts)
    query_ids = validate_queries(root)
    validate_relations(root, extracts)
    validate_ledger(root, query_ids, set(extracts))


def validate_resolution_manifest(root: Path) -> str:
    assert {path.name for path in root.iterdir()} == ARTIFACT_NAMES, (
        "resolution.manifest.artifact_set.exact"
    )
    manifest = _json(root / "packet-manifest.json")
    artifact_digests = _mapping(manifest["artifact_sha256"])
    assert artifact_digests == EVIDENCE_ARTIFACTS, "resolution.manifest.graph.closed"
    for name, expected in artifact_digests.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, (
            f"resolution.manifest.artifact_sha256.match:{name}"
        )
    preimage = json.dumps(artifact_digests, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(preimage).hexdigest()
    assert manifest["packet_digest"] == digest, "resolution.manifest.packet_digest.match"
    return digest


def validate_resolution_packet(root: Path) -> str:
    validate_resolution_semantics(root)
    return validate_resolution_manifest(root)
