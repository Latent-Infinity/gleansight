from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonPathElement = str | int

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PACKET_ROOT: Final = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-resolution-2026-09-09"
)


@dataclass(frozen=True, slots=True)
class TamperCase:
    name: str
    artifact: str
    path: tuple[JsonPathElement, ...]
    replacement: JsonValue
    guard: str


TAMPER_CASES: Final = (
    TamperCase(
        "budget_widening",
        "bibliographic-query-receipts.json",
        ("maximum_query_batches",),
        4,
        "resolution.query.budget.frozen",
    ),
    TamperCase(
        "duplicate_source_identity",
        "acquisition-receipts.json",
        ("records", 1, "stable_source_id"),
        "arXiv:2602.04643",
        "resolution.acquisition.identity.unique",
    ),
    TamperCase(
        "bad_retention_state",
        "acquisition-receipts.json",
        ("records", 0, "retention", "state"),
        "retained_repository_authorized",
        "resolution.retention.state.match",
    ),
    TamperCase(
        "bad_retention_fields",
        "acquisition-receipts.json",
        ("records", 0, "retention"),
        {},
        "resolution.retention.fields.exact",
    ),
    TamperCase(
        "retained_pdf_path",
        "acquisition-receipts.json",
        ("records", 0, "retention", "repository_path_or_null"),
        "source.pdf",
        "resolution.retention.repository_path.null",
    ),
    TamperCase(
        "quote_digest",
        "source-extracts.jsonl",
        (0, "quote_sha256"),
        "0" * 64,
        "resolution.extract.quote_sha256.match",
    ),
    TamperCase(
        "extract_receipt_digest",
        "source-extracts.jsonl",
        (0, "source_sha256"),
        "0" * 64,
        "resolution.extract.receipt_digest.match",
    ),
    TamperCase(
        "missing_relation_field",
        "typed-relations.json",
        ("A_to_bridge", "source"),
        {},
        "resolution.relation.fields.exact",
    ),
    TamperCase(
        "relation_passage_mismatch",
        "typed-relations.json",
        ("bridge_to_C", "target", "passage"),
        "unbound passage",
        "resolution.relation.passage.bound",
    ),
    TamperCase(
        "positive_polarity",
        "typed-relations.json",
        ("A_to_bridge", "source", "polarity"),
        "supported",
        "resolution.relation.polarity.unsupported",
    ),
    TamperCase(
        "accepted_bridge",
        "typed-relations.json",
        ("accepted_bridge",),
        True,
        "resolution.relation.accepted_bridge.false",
    ),
    TamperCase(
        "unknown_query_reference",
        "evidence-ledger.json",
        ("interaction_checks", 0, "query_receipt_ids"),
        ["unknown-query"],
        "resolution.ledger.query_references.known",
    ),
    TamperCase(
        "unavailable_mislabeled_as_absence",
        "bibliographic-query-receipts.json",
        ("query_batches", 0, "records", 4, "observation_state"),
        "not_observed_within_bounded_queries",
        "resolution.query.unavailable.not_absence",
    ),
    TamperCase(
        "candidate_output",
        "evidence-ledger.json",
        ("candidate_outputs",),
        ["candidate"],
        "resolution.ledger.outputs.empty",
    ),
    TamperCase(
        "candidate_combination",
        "evidence-ledger.json",
        ("candidate_combinations",),
        ["combination"],
        "resolution.ledger.combinations.empty",
    ),
    TamperCase(
        "authority_escalation",
        "evidence-ledger.json",
        ("runtime_authorized",),
        True,
        "resolution.ledger.runtime.false",
    ),
)


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
            case unexpected:
                raise AssertionError(unexpected)
    match current, path[-1]:
        case dict() as mapping, str() as key:
            mapping[key] = replacement
        case list() as sequence, int() as index:
            sequence[index] = replacement
        case unexpected:
            raise AssertionError(unexpected)


def _tampered_packet(tmp_path: Path, case: TamperCase, *, rehash: bool = False) -> Path:
    packet = tmp_path / case.name
    shutil.copytree(PACKET_ROOT, packet)
    artifact = packet / case.artifact
    if artifact.suffix == ".jsonl":
        payload: JsonValue = [json.loads(line) for line in artifact.read_text().splitlines()]
    else:
        payload = json.loads(artifact.read_text())
    _set_value(payload, case.path, case.replacement)
    if artifact.suffix == ".jsonl":
        assert isinstance(payload, list)
        artifact.write_text("\n".join(json.dumps(row) for row in payload) + "\n")
    else:
        artifact.write_text(json.dumps(payload))
    if rehash:
        _rehash_manifest(packet, case.artifact)
    return packet


def _rehash_manifest(packet: Path, artifact_name: str) -> None:
    manifest_path = packet / "packet-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    artifact_digests = manifest["artifact_sha256"]
    artifact_digests[artifact_name] = hashlib.sha256(
        (packet / artifact_name).read_bytes()
    ).hexdigest()
    preimage = json.dumps(artifact_digests, sort_keys=True, separators=(",", ":")).encode()
    manifest["packet_digest"] = hashlib.sha256(preimage).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
