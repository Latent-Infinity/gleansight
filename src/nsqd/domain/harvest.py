from __future__ import annotations

import json
from typing import Any

from nsqd.domain.card import corpus_ingest_rejection

ALLOWED_RECORD_TYPES = frozenset({"paper", "code", "benchmark"})
IMMUTABLE_RECORD_FIELDS = (
    "domain_policy_id",
    "coordinates",
    "provenance",
    "tags",
    "aliases",
    "retracted",
    "invalid_reason",
)
OPTIONAL_RECORD_FIELDS = (
    "coordinates",
    "provenance",
    "tags",
    "aliases",
    "retracted",
    "invalid_reason",
)
MAX_HARVEST_RECORDS = 10_000
MAX_PARAPHRASE_LENGTH = 100_000
MAX_SOURCE_LENGTH = 8_192
MAX_METADATA_BYTES = 65_536


class HarvestRejected(ValueError):
    """Raised when a harvest payload is essay-only or otherwise not enumerable."""


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def harvest_record_rejection(record: dict[str, Any]) -> str | None:
    card_reason = corpus_ingest_rejection(record)
    if card_reason is not None:
        return card_reason
    policy_id = record.get("domain_policy_id")
    if not isinstance(policy_id, str) or not policy_id.strip():
        return "domain_policy_id is required"
    for field in ("type", "paraphrase", "source"):
        value = record.get(field)
        if value is not None and not isinstance(value, str):
            return f"{field} must be a string"
    rec_type = record.get("type")
    if _blank(rec_type):
        return "missing record type"
    if rec_type not in ALLOWED_RECORD_TYPES:
        return "unsupported record type"
    if _blank(record.get("paraphrase")):
        return "empty paraphrase"
    if _blank(record.get("source")):
        return "sourceless"
    paraphrase = record["paraphrase"]
    source = record["source"]
    assert isinstance(paraphrase, str)
    assert isinstance(source, str)
    if len(paraphrase) > MAX_PARAPHRASE_LENGTH:
        return "paraphrase is too long"
    if len(source) > MAX_SOURCE_LENGTH:
        return "source is too long"
    metadata_reason = _optional_metadata_rejection(record)
    if metadata_reason is not None:
        return metadata_reason
    return None


def immutable_record_conflict(existing: dict[str, Any], incoming: dict[str, Any]) -> str | None:
    for field in IMMUTABLE_RECORD_FIELDS:
        if field in incoming and existing.get(field) != incoming[field]:
            return f"immutable metadata conflict: {field}"
    return None


def _optional_metadata_rejection(record: dict[str, Any]) -> str | None:
    for field in ("coordinates", "provenance"):
        if field in record and not isinstance(record[field], dict):
            return f"{field} must be a mapping"
    for field in ("tags", "aliases"):
        if field in record and (
            not isinstance(record[field], list)
            or not all(isinstance(item, str) for item in record[field])
        ):
            return f"{field} must be a list of strings"
    if "retracted" in record and not isinstance(record["retracted"], bool):
        return "retracted must be a boolean"
    if "invalid_reason" in record and not isinstance(record["invalid_reason"], str):
        return "invalid_reason must be a string"
    metadata = {field: record[field] for field in OPTIONAL_RECORD_FIELDS if field in record}
    try:
        encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError, RecursionError):
        return "optional metadata must be JSON-compatible"
    if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
        return "optional metadata is too large"
    return None


def is_essay_payload(payload: Any) -> bool:
    if isinstance(payload, str):
        return True
    if isinstance(payload, list):
        return len(payload) == 0 or not all(isinstance(item, dict) for item in payload)
    if not isinstance(payload, dict):
        return True
    kind = str(payload.get("kind") or "")
    if kind in {"essay", "essay-only"}:
        return True
    if kind == "candidate-requirement-card":
        return False
    if isinstance(payload.get("records"), list):
        return False
    if "type" in payload and "paraphrase" in payload and "source" in payload:
        return False
    return True


def harvest_records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if is_essay_payload(payload):
        raise HarvestRejected("essay-only ingest is rejected")
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
        records = payload["records"]
    else:
        records = [payload]
    if not records:
        raise HarvestRejected("essay-only ingest is rejected")
    if len(records) > MAX_HARVEST_RECORDS:
        raise HarvestRejected("too many harvest records")
    accepted: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            raise HarvestRejected("essay-only ingest is rejected")
        reason = harvest_record_rejection(item)
        if reason is not None:
            raise HarvestRejected(reason)
        accepted.append(item)
    return accepted
