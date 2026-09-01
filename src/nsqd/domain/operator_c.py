from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PAIR_NAMES = frozenset({"preferred", "backup"})
S2_PAPER_ID_LENGTH = 40
NONINTERACTION_UNVERIFIED = "local approved projections do not bind author or citation graphs"


def classify_source_paper_id(source_paper_id: object) -> str:
    if not isinstance(source_paper_id, str) or not source_paper_id.strip():
        raise ValueError("source_paper_id is required")
    value = source_paper_id.strip()
    lowered = value.lower()
    if lowered.startswith("doi:"):
        return "doi"
    if lowered.startswith("arxiv:"):
        return "arxiv"
    if len(value) == S2_PAPER_ID_LENGTH and all(char in "0123456789abcdefABCDEF" for char in value):
        return "s2"
    return "unknown"


def bind_operator_c_pair(
    packet: Mapping[str, object],
    *,
    approved_records: Mapping[str, Mapping[str, object]],
    pair: str = "preferred",
) -> dict[str, Any]:
    if packet.get("operator") != "C":
        raise ValueError("operator C binder requires operator C packet")
    if packet.get("authorization_state") != "report_only":
        raise ValueError("operator C binder requires report_only authorization_state")
    if packet.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if packet.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    candidate_outputs = packet.get("candidate_outputs")
    if not isinstance(candidate_outputs, list) or candidate_outputs:
        raise ValueError("operator C candidate_outputs must be an empty list")
    algorithm_identity = _required_string(packet, "algorithm_identity")
    if pair not in PAIR_NAMES:
        raise ValueError("pair must be preferred or backup")
    pair_payload = _required_string_keyed_mapping(packet.get(f"{pair}_pair"), f"{pair}_pair")
    literature_a = _bind_literature(
        pair_payload,
        role="literature_a",
        approved_records=approved_records,
    )
    literature_c = _bind_literature(
        pair_payload,
        role="literature_c",
        approved_records=approved_records,
    )
    if literature_a["source_paper_id"] == literature_c["source_paper_id"]:
        raise ValueError("operator C pair requires distinct literatures")
    if literature_a["domain_policy_id"] == literature_c["domain_policy_id"]:
        raise ValueError("operator C pair requires distinct domain policies")
    return {
        "pair": pair,
        "literature_a": literature_a,
        "literature_c": literature_c,
        "noninteraction": {
            "status": "unverified",
            "reason": NONINTERACTION_UNVERIFIED,
        },
        "evidence_sufficient": False,
        "runtime_authorized": False,
        "algorithm_identity": algorithm_identity,
    }


def _bind_literature(
    pair_payload: Mapping[str, object],
    *,
    role: str,
    approved_records: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    declared = _required_string_keyed_mapping(pair_payload.get(role), role)
    record_id = _required_string(declared, "record_id")
    record = approved_records.get(record_id)
    if record is None:
        raise ValueError(f"unknown record {record_id}")
    if record.get("kind") != "corpus-paper-paraphrase":
        raise ValueError("operator C records must be approved paraphrases")
    if record.get("review_status") != "approved":
        raise ValueError("operator C records must be approved")
    domain_policy_id = _required_string(record, "domain_policy_id")
    declared_policy = declared.get("domain_policy_id")
    if declared_policy is not None and declared_policy != domain_policy_id:
        raise ValueError("literature domain_policy_id does not match approved record")
    source_paper_id = _required_string(record, "source_paper_id")
    title = _required_string(record, "title")
    declared_title = declared.get("title")
    if declared_title is not None and declared_title != title:
        raise ValueError("literature title does not match approved record")
    return {
        "record_id": record_id,
        "domain_policy_id": domain_policy_id,
        "title": title,
        "source_paper_id": source_paper_id,
        "identifier_scheme": classify_source_paper_id(source_paper_id),
    }


def _required_string_keyed_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is required")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field} keys must be strings")
        result[key] = item
    return result


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()
