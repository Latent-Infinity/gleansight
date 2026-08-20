from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timedelta
from typing import Any


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def is_utc_datetime(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def is_utc_datetime_or_iso(value: object) -> bool:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    return is_utc_datetime(value)


def normalize_source(source: str) -> str:
    text = unicodedata.normalize("NFC", source).strip().replace("\r\n", "\n").replace("\r", "\n")
    lowered = text.casefold()
    if lowered.startswith("doi:"):
        rest = text[4:].strip()
        return _normalize_doi(rest)
    if "doi.org/" in lowered:
        rest = text[lowered.index("doi.org/") + len("doi.org/") :]
        return _normalize_doi(rest)
    if lowered.startswith("10."):
        return _normalize_doi(text)
    if lowered.startswith("http://") or lowered.startswith("https://"):
        no_frag = text.split("#", 1)[0]
        scheme, _, rest = no_frag.partition("://")
        host, sep, path = rest.partition("/")
        normalized = f"{scheme.casefold()}://{host.casefold()}"
        if sep:
            normalized = f"{normalized}/{path}"
        return normalized.rstrip("/")
    return text


def _normalize_doi(value: str) -> str:
    rest = value.strip().removeprefix("https://").removeprefix("http://")
    rest = rest.removeprefix("doi.org/")
    rest = rest.rstrip("/")
    return f"doi:{rest.casefold()}"


def record_content_hash(*, type: str, paraphrase: str, source: str) -> str:
    paraphrase_nfc = (
        unicodedata.normalize("NFC", paraphrase).replace("\r\n", "\n").replace("\r", "\n")
    )
    preimage = {
        "paraphrase": paraphrase_nfc,
        "source": normalize_source(source),
        "type": type,
    }
    return sha256_hex(canonical_json(preimage))


def snapshot_id(*, records: list[dict[str, str]], schema_version: int) -> str:
    ordered = sorted(
        ({"content_hash": row["content_hash"], "record_id": row["record_id"]} for row in records),
        key=lambda row: row["record_id"],
    )
    seen_record_ids: set[str] = set()
    for row in ordered:
        if row["record_id"] in seen_record_ids:
            raise ValueError("duplicate record_id")
        seen_record_ids.add(row["record_id"])
    preimage = {"records": ordered, "schema_version": schema_version}
    return sha256_hex(canonical_json(preimage))
