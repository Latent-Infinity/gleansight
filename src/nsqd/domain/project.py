from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any

from nsqd.domain.snapshot import canonical_json, normalize_source, sha256_hex

DATA_NSQD_04_SOURCE_PAPER_ID = "7dbcef75-2d52-49a6-86a3-471be71f0fd7"
DATA_NSQD_04_PAPER_ID = "paper-20"
PROJECTOR_VERSION = "paper-projector/1"
REVIEWED_PROJECTION_FIELDS = (
    "domain_policy_id",
    "paraphrase",
    "paraphrase_source",
    "source_paper_id",
    "source",
    "coordinates",
    "source_abstract_sha256",
    "source_markdown_sha256",
    "paraphrase_sha256",
    "human_reviewer",
    "human_approved_at",
    "review_status",
)


def normalize_paraphrase(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").strip()


def is_data_nsqd_04(projection: dict[str, Any]) -> bool:
    if str(projection.get("id") or "") == "DATA-NSQD-04":
        return True
    source = str(projection.get("source_paper_id") or "")
    paper_id = str(projection.get("paper_id") or "")
    return source == DATA_NSQD_04_SOURCE_PAPER_ID or paper_id == DATA_NSQD_04_PAPER_ID


def is_abstract_substitution(*, paraphrase: str, abstract: str | None) -> bool:
    if abstract is None or not abstract.strip():
        return False
    return normalize_paraphrase(paraphrase) == normalize_paraphrase(abstract)


def projection_identity(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(record.get("source_paper_id") or ""),
        str(record.get("domain_policy_id") or ""),
        str(record.get("source_abstract_sha256") or ""),
        str(record.get("source_markdown_sha256") or ""),
        str(record.get("paraphrase_sha256") or ""),
    )


def projection_record_id(record: dict[str, Any]) -> str:
    (
        source_paper_id,
        domain_policy_id,
        source_abstract_sha256,
        source_markdown_sha256,
        paraphrase_sha256,
    ) = projection_identity(record)
    preimage = {
        "domain_policy_id": domain_policy_id,
        "paraphrase_sha256": paraphrase_sha256,
        "source_abstract_sha256": source_abstract_sha256,
        "source_markdown_sha256": source_markdown_sha256,
        "source_paper_id": source_paper_id,
    }
    return sha256_hex(canonical_json(preimage))


def canonical_reviewed_projection_digest(projection: dict[str, Any]) -> str:
    return sha256_hex(canonical_reviewed_projection_bytes(projection))


def canonical_reviewed_projection_bytes(projection: dict[str, Any]) -> bytes:
    return canonical_json(_reviewed_projection_contract(projection))


def _reviewed_projection_contract(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _normalize_reviewed_field(key, projection[key])
        for key in REVIEWED_PROJECTION_FIELDS
        if key in projection
    }


def _normalize_reviewed_field(key: str, value: Any) -> Any:
    if isinstance(value, datetime):
        value = value.isoformat()
    if key == "paraphrase" and isinstance(value, str):
        return normalize_paraphrase(value)
    if key == "source" and isinstance(value, str):
        return normalize_source(value)
    if key == "coordinates" and isinstance(value, dict):
        return {
            axis_name: normalize_paraphrase(axis_value)
            if isinstance(axis_value, str)
            else axis_value
            for axis_name, axis_value in value.items()
        }
    if key in {
        "domain_policy_id",
        "human_approved_at",
        "human_reviewer",
        "paraphrase_sha256",
        "paraphrase_source",
        "review_status",
        "source_abstract_sha256",
        "source_markdown_sha256",
        "source_paper_id",
    } and isinstance(value, str):
        return value.strip()
    return value
