from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from nsqd.domain.policy import FINANCE_POLICY, OPTIMIZATION_POLICY
from nsqd.domain.sufficiency import (
    SUFFICIENCY_FAILURES,
    decide_snapshot_state,
    evaluate_sufficiency,
)

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIN_CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"
OPT_CELL = "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"
EMPTY_FINANCE_POLICY = replace(
    FINANCE_POLICY,
    expected_cells=frozenset(),
    recall_probes=(),
    required_record_types={"paper": 0, "code": 0, "benchmark": 0},
    min_records=0,
)


def _paper(
    *,
    policy: str,
    source: str,
    paraphrase: str = "a mechanism",
    rec_type: str = "paper",
    content_hash: str = "abc",
    coordinates: dict[str, str] | None = None,
    **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "type": rec_type,
        "paraphrase": paraphrase,
        "source": source,
        "content_hash": content_hash,
        "domain_policy_id": policy,
        "harvested_at": AS_OF,
    }
    if coordinates is not None:
        row["coordinates"] = coordinates
    row.update(extra)
    return row


def test_closed_failure_set_is_complete() -> None:
    assert SUFFICIENCY_FAILURES == frozenset(
        {
            "expected_cell_empty",
            "recall_probe_missing",
            "disagreement_unresolved",
            "record_metadata_missing",
            "duplicate_source_conflict",
            "retracted_unmarked",
            "domain_minima_unmet",
            "manifest_missing",
        }
    )


@pytest.mark.parametrize(
    ("records", "kwargs", "expected"),
    [
        (
            [],
            {
                "policy": replace(
                    EMPTY_FINANCE_POLICY,
                    expected_cells=frozenset({FIN_CELL}),
                )
            },
            ("expected_cell_empty",),
        ),
        (
            [],
            {
                "policy": replace(
                    EMPTY_FINANCE_POLICY,
                    recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
                )
            },
            ("recall_probe_missing",),
        ),
        (
            [_paper(policy="finance/1", source="doi:10.1/a")],
            {"policy": EMPTY_FINANCE_POLICY, "disagreement": True},
            ("disagreement_unresolved",),
        ),
        (
            [{"domain_policy_id": "finance/1", "type": "paper", "paraphrase": "x"}],
            {"policy": EMPTY_FINANCE_POLICY},
            ("record_metadata_missing",),
        ),
        (
            [
                _paper(
                    policy="finance/1", source="doi:10.1/dup", paraphrase="one", content_hash="1"
                ),
                _paper(
                    policy="finance/1", source="doi:10.1/dup", paraphrase="two", content_hash="2"
                ),
            ],
            {"policy": EMPTY_FINANCE_POLICY},
            ("duplicate_source_conflict",),
        ),
        (
            [
                _paper(
                    policy="finance/1",
                    source="doi:10.1/dead",
                    retraction_notice="withdrawn",
                )
            ],
            {"policy": EMPTY_FINANCE_POLICY},
            ("retracted_unmarked",),
        ),
        (
            [_paper(policy="finance/1", source="doi:10.1/a")],
            {"policy": replace(EMPTY_FINANCE_POLICY, min_records=2)},
            ("domain_minima_unmet",),
        ),
        (
            [],
            {"policy": EMPTY_FINANCE_POLICY, "approved_manifest": False},
            ("manifest_missing",),
        ),
    ],
)
def test_each_sufficiency_failure_code(
    records: list[dict[str, object]],
    kwargs: dict[str, Any],
    expected: tuple[str, ...],
) -> None:
    failures = evaluate_sufficiency(records, as_of=AS_OF, **kwargs)
    assert failures == expected


def test_finance_and_optimization_verdicts_are_independent() -> None:
    opt_policy = replace(
        OPTIMIZATION_POLICY,
        recall_probes=(("opt-probe", "doi:10.1/opt", "paper"),),
        expected_cells=frozenset({OPT_CELL}),
        min_records=1,
    )
    records = [
        _paper(
            policy="optimization/1",
            source="doi:10.1/opt",
            coordinates={
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
        )
    ]
    finance = evaluate_sufficiency(records, policy=FINANCE_POLICY, as_of=AS_OF)
    optimization = evaluate_sufficiency(records, policy=opt_policy, as_of=AS_OF)
    assert finance == (
        "recall_probe_missing",
        "expected_cell_empty",
        "domain_minima_unmet",
    )
    assert optimization == ()
    finance_empty_expected = evaluate_sufficiency(
        records,
        policy=replace(EMPTY_FINANCE_POLICY, expected_cells=frozenset({FIN_CELL})),
        as_of=AS_OF,
    )
    assert finance_empty_expected == ("expected_cell_empty",)


def test_cross_pack_records_cannot_satisfy_the_other_policy() -> None:
    opt_policy = replace(
        OPTIMIZATION_POLICY,
        recall_probes=(("opt-probe", "doi:10.1/opt", "paper"),),
        min_records=1,
    )
    finance_records = [_paper(policy="finance/1", source="doi:10.1/opt")]
    failures = evaluate_sufficiency(finance_records, policy=opt_policy, as_of=AS_OF)
    assert "recall_probe_missing" in failures
    assert "domain_minima_unmet" in failures


def test_calibration_allows_pending_minima_but_not_integrity_failures() -> None:
    pending = ("expected_cell_empty", "domain_minima_unmet")
    assert decide_snapshot_state(pending, target="calibration") == "calibration"
    assert (
        decide_snapshot_state(("record_metadata_missing",), target="calibration") == "insufficient"
    )
    assert decide_snapshot_state((), target="calibration", recall_probe_listed=False) == (
        "insufficient"
    )


def test_finance_production_valid_requires_approved_harvest_seed() -> None:
    assert (
        decide_snapshot_state(
            (),
            target="production_valid",
            domain_policy_id="finance/1",
            harvest_seed_approved=False,
        )
        == "insufficient"
    )
    assert (
        decide_snapshot_state(
            (),
            target="production_valid",
            domain_policy_id="finance/1",
            harvest_seed_approved=True,
        )
        == "production_valid"
    )
    assert decide_snapshot_state(("expected_cell_empty",), target="production_valid") == (
        "insufficient"
    )


def test_invalid_record_cannot_satisfy_recall_probe() -> None:
    policy = replace(
        FINANCE_POLICY,
        recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
    )
    failures = evaluate_sufficiency(
        [
            _paper(
                policy="finance/1",
                source="doi:10.1/a",
                invalid_reason="failed review",
            )
        ],
        policy=policy,
        as_of=AS_OF,
    )
    assert "recall_probe_missing" in failures


def test_retracted_record_cannot_satisfy_recall_or_minima() -> None:
    policy = replace(
        FINANCE_POLICY,
        recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
        min_records=1,
    )
    failures = evaluate_sufficiency(
        [_paper(policy="finance/1", source="doi:10.1/a", retracted=True)],
        policy=policy,
        as_of=AS_OF,
    )
    assert "recall_probe_missing" in failures
    assert "domain_minima_unmet" in failures
