from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType
from typing import Any

from nsqd.domain.descriptor import HORIZON_VALUES, MECHANISM_VALUES, TARGET_VALUES


class UnknownDomainPolicy(ValueError):
    """Raised when domain_policy_id is missing from the registry."""


class IncompatibleDvalRubric(ValueError):
    """Raised when a candidate dval rubric is not listed on the selected policy."""


@dataclass(frozen=True)
class DomainPolicy:
    policy_id: str
    axes: tuple[tuple[str, frozenset[str]], ...]
    dval_rubric_ids: frozenset[str]
    expected_cells: frozenset[str]
    recall_probes: tuple[tuple[str, str, str], ...]
    required_record_types: Mapping[str, int]
    min_records: int

    def universe(self) -> frozenset[str]:
        names = [name for name, _values in self.axes]
        value_sets = [sorted(values) for _name, values in self.axes]
        return frozenset(
            "|".join(f"{name}={value}" for name, value in zip(names, combo, strict=True))
            for combo in product(*value_sets)
        )

    def cell_id(self, descriptor: dict[str, Any]) -> str:
        parts: list[str] = []
        for name, values in self.axes:
            value = descriptor.get(name)
            if value not in values:
                raise ValueError("unlisted research descriptor value")
            parts.append(f"{name}={value}")
        return "|".join(parts)


FINANCE_POLICY = DomainPolicy(
    policy_id="finance/1",
    axes=(
        ("mechanism", MECHANISM_VALUES),
        ("target", TARGET_VALUES),
        ("horizon", HORIZON_VALUES),
    ),
    dval_rubric_ids=frozenset({"r1", "finance-dval/1", "finance/dval/1"}),
    expected_cells=frozenset(),
    recall_probes=(),
    required_record_types=MappingProxyType({"paper": 0, "code": 0, "benchmark": 0}),
    min_records=0,
)

OPTIMIZATION_POLICY = DomainPolicy(
    policy_id="optimization/1",
    axes=(
        ("problem", frozenset({"constrained-expectation", "unconstrained"})),
        ("method", frozenset({"sequential-quadratic", "first-order"})),
        ("setting", frozenset({"rank-deficient", "full-rank"})),
    ),
    dval_rubric_ids=frozenset({"optimization-dval/1"}),
    expected_cells=frozenset(),
    recall_probes=(),
    required_record_types=MappingProxyType({"paper": 0, "code": 0, "benchmark": 0}),
    min_records=0,
)

POLICIES: Mapping[str, DomainPolicy] = MappingProxyType(
    {
        FINANCE_POLICY.policy_id: FINANCE_POLICY,
        OPTIMIZATION_POLICY.policy_id: OPTIMIZATION_POLICY,
    }
)


def require_domain_policy_id(payload: dict[str, Any]) -> str:
    value = payload.get("domain_policy_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("domain_policy_id is required")
    return value.strip()


def get_policy(policy_id: str) -> DomainPolicy:
    try:
        return POLICIES[policy_id]
    except KeyError as exc:
        raise UnknownDomainPolicy(f"unknown domain_policy_id: {policy_id}") from exc


def records_for_policy(
    records: list[dict[str, Any]],
    policy_id: str,
) -> list[dict[str, Any]]:
    return [row for row in records if row.get("domain_policy_id") == policy_id]


def verdict_key(*, snapshot_id: str, domain_policy_id: str) -> tuple[str, str]:
    get_policy(domain_policy_id)
    if not snapshot_id:
        raise ValueError("snapshot_id is required")
    return (snapshot_id, domain_policy_id)


def archive_cell_key(*, domain_policy_id: str, cell_id: str) -> str:
    get_policy(domain_policy_id)
    if not cell_id:
        raise ValueError("cell_id is required")
    return f"{domain_policy_id}::{cell_id}"


def require_compatible_dval_rubric(candidate: dict[str, Any], policy: DomainPolicy) -> None:
    assignment = candidate.get("dval")
    if not isinstance(assignment, dict):
        return
    rubric_id = assignment.get("rubric_id")
    if rubric_id is None or rubric_id == "":
        return
    if rubric_id not in policy.dval_rubric_ids:
        raise IncompatibleDvalRubric(
            f"incompatible dval rubric {rubric_id!r} for {policy.policy_id}"
        )
