from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

E_POLICIES = ("finance/1", "optimization/1")


def bind_operator_e_inventory(
    packet: Mapping[str, object],
    *,
    approved_records: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    if packet.get("operator") != "E":
        raise ValueError("operator E binder requires operator E packet")
    if packet.get("authorization_state") != "report_only":
        raise ValueError("operator E binder requires report_only authorization_state")
    if packet.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if packet.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    combinations = packet.get("candidate_combinations")
    if not isinstance(combinations, list) or combinations:
        raise ValueError(
            "operator E candidate combinations: candidate_combinations must be an empty list"
        )
    candidate_outputs = packet.get("candidate_outputs")
    if not isinstance(candidate_outputs, list) or candidate_outputs:
        raise ValueError("operator E candidate_outputs must be an empty list")
    inventory = _required_string_keyed_mapping(
        packet.get("approved_component_inventory"),
        "approved_component_inventory",
    )
    same_policy: dict[str, list[str]] = {}
    for policy_id in E_POLICIES:
        record_ids = _required_string_list(inventory.get(policy_id), policy_id)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError(f"operator E inventory for {policy_id} has a duplicate record_id")
        bound_ids: list[str] = []
        for record_id in record_ids:
            record = approved_records.get(record_id)
            if record is None:
                raise ValueError(f"unknown record {record_id}")
            if record.get("kind") == "candidate-requirement-card":
                raise ValueError("requirement-card is not an Operator E component")
            if record.get("kind") != "corpus-paper-paraphrase":
                raise ValueError("operator E records must be approved paraphrases")
            if record.get("review_status") != "approved":
                raise ValueError("operator E records must be approved")
            record_policy = _required_string(record, "domain_policy_id")
            if record_policy != policy_id:
                raise ValueError("component domain_policy_id does not match inventory policy")
            bound_ids.append(record_id)
        same_policy[policy_id] = bound_ids
    unexpected = set(inventory) - set(E_POLICIES)
    if unexpected:
        raise ValueError("operator E inventory contains unknown domain policies")
    return {
        "tracks": {
            "same_policy": same_policy,
            "cross_policy": {
                "pooled": False,
                "source_domain_policy_ids": list(E_POLICIES),
                "target_domain_policy_ids": list(E_POLICIES),
            },
        },
        "candidate_combinations": [],
        "co_occurrence_snapshot_id": None,
        "evidence_sufficient": False,
        "runtime_authorized": False,
        "algorithm_identity": "not_run",
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


def _required_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} is required")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} values must be strings")
        result.append(item.strip())
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()
