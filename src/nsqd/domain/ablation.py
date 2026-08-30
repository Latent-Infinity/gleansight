from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from nsqd.domain.acquisition import (
    CANDIDATES_PER_BATCH,
    QUERY_BATCH_LIMIT,
    RECHECK_CYCLE_LIMIT,
    STAGED_IMPORT_LIMIT,
)
from nsqd.domain.novelty import NOVELTY_BIN_EDGES, NOVELTY_K, NOVELTY_THRESHOLD_TAU
from nsqd.domain.status import DEFAULT_DENSITY_CUT, STATUS_WINDOW_DAYS, CellStatus, cell_status

AXIS_KEEP_SUM = 4
DENSITY_CUTS = (2, 3, 5)


@dataclass(frozen=True)
class ProposedAxisTriple:
    axis_id: str
    axes: tuple[str, ...]
    cardinalities: tuple[int, ...]
    scores: tuple[int, int, int]


@dataclass(frozen=True)
class LabeledStatusCell:
    cell_id: str
    records: tuple[dict[str, Any], ...]
    inspected: bool
    expected: bool
    invalid_reason: str | None
    disagreement: bool
    method_claims_evaluation: bool
    expected_status: CellStatus


def keep_axis_triple(scores: tuple[int, ...]) -> bool:
    if len(scores) != 3:
        raise ValueError("axis criterion scores must include exactly 3 criteria")
    if any(score not in {0, 1, 2} for score in scores):
        raise ValueError("axis criterion scores must be 0-2")
    return sum(scores) >= AXIS_KEEP_SUM


def proposed_axis_triples() -> tuple[ProposedAxisTriple, ...]:
    return (
        ProposedAxisTriple(
            axis_id="finance-v1-mechanism-target-horizon",
            axes=("mechanism", "target", "horizon"),
            cardinalities=(7, 8, 6),
            scores=(2, 2, 2),
        ),
        ProposedAxisTriple(
            axis_id="finance-v1-plus-tick-bucket",
            axes=("mechanism", "target", "horizon", "tick-bucket"),
            cardinalities=(7, 8, 6, 50),
            scores=(1, 2, 0),
        ),
        ProposedAxisTriple(
            axis_id="color-flavor",
            axes=("color", "flavor"),
            cardinalities=(5, 5),
            scores=(0, 0, 2),
        ),
    )


def labeled_status_cells(*, as_of: datetime) -> tuple[LabeledStatusCell, ...]:
    recent = as_of - timedelta(days=10)
    paper = {"type": "paper", "harvested_at": recent}
    code = {"type": "code", "harvested_at": recent}
    return (
        LabeledStatusCell("unknown-empty", (), False, False, None, False, False, "Unknown"),
        LabeledStatusCell("missing", (), True, True, None, False, False, "Missing"),
        LabeledStatusCell(
            "code-gap",
            (paper,),
            True,
            False,
            None,
            False,
            False,
            "Code-gap",
        ),
        LabeledStatusCell(
            "sparse-pair",
            (paper, code),
            True,
            False,
            None,
            False,
            False,
            "Sparse",
        ),
        LabeledStatusCell(
            "active-three",
            (paper, paper, code),
            True,
            False,
            None,
            False,
            False,
            "Active",
        ),
        LabeledStatusCell(
            "active-four",
            (paper, paper, paper, code),
            True,
            False,
            None,
            False,
            False,
            "Active",
        ),
        LabeledStatusCell(
            "mature",
            (paper, paper, paper, paper, paper, code),
            True,
            False,
            None,
            False,
            False,
            "Mature",
        ),
        LabeledStatusCell(
            "stalled",
            ({"type": "paper", "tags": ["abandoned"]},),
            True,
            False,
            None,
            False,
            False,
            "Stalled",
        ),
        LabeledStatusCell(
            "future-work",
            ({"type": "paper", "tags": ["future_work"]},),
            True,
            False,
            None,
            False,
            False,
            "Future-work-only",
        ),
        LabeledStatusCell(
            "invalid",
            (),
            True,
            False,
            "bad-cell",
            False,
            False,
            "Invalid",
        ),
    )


def density_cut_agreement(
    cases: tuple[LabeledStatusCell, ...],
    *,
    as_of: datetime,
) -> dict[int, int]:
    scores: dict[int, int] = {}
    for cut in DENSITY_CUTS:
        matched = 0
        for case in cases:
            predicted = cell_status(
                list(case.records),
                as_of=as_of,
                snapshot_state="calibration",
                inspected=case.inspected,
                expected=case.expected,
                invalid_reason=case.invalid_reason,
                disagreement=case.disagreement,
                method_claims_evaluation=case.method_claims_evaluation,
                density_cut=cut,
            )
            if predicted == case.expected_status:
                matched += 1
        scores[cut] = matched
    return scores


def select_density_cut(agreements: dict[int, int]) -> int:
    if not agreements:
        raise ValueError("agreements must not be empty")
    best = max(agreements.values())
    if best < 8:
        raise ValueError("no density cut reached 8/10 agreement")
    winners = [cut for cut, score in agreements.items() if score == best]
    if DEFAULT_DENSITY_CUT in winners:
        return DEFAULT_DENSITY_CUT
    return min(winners)


def viability_keeps_presence_stubs() -> bool:
    return True


FreezeOutcome = Literal["approved_default_tunable", "frozen", "deferred", "unset", "rejected"]


@dataclass(frozen=True)
class AlgFamilyDecision:
    family_id: str
    outcome: FreezeOutcome
    freeze_approved: bool
    current_default: str
    reopen: str


def alg_family_decisions() -> tuple[AlgFamilyDecision, ...]:
    return (
        AlgFamilyDecision(
            family_id="ALG.AXES",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default="finance v1 mechanism × target × horizon",
            reopen="a second pack needs a different archive triple",
        ),
        AlgFamilyDecision(
            family_id="ALG.K",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default=str(NOVELTY_K),
            reopen="production-valid calibration repeat of leave-one-out Spearman",
        ),
        AlgFamilyDecision(
            family_id="ALG.NOVELTY_BINS",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default="/".join(str(edge) for edge in NOVELTY_BIN_EDGES),
            reopen="labeled novelty-term disagreements on calibration or production_valid",
        ),
        AlgFamilyDecision(
            family_id="ALG.NOV.TAU",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default=str(NOVELTY_THRESHOLD_TAU),
            reopen="production-valid calibration repeat or policy-specific false-kill drift",
        ),
        AlgFamilyDecision(
            family_id="ALG.STATUS.THRESHOLDS",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default=str(DEFAULT_DENSITY_CUT),
            reopen="production-valid map labels disagree with density cut 3",
        ),
        AlgFamilyDecision(
            family_id="ALG.STATUS.WINDOW",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default=f"{STATUS_WINDOW_DAYS}-day",
            reopen="production map looks uniformly Stalled or uniformly Active",
        ),
        AlgFamilyDecision(
            family_id="ALG.VIABILITY",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default="0/5 presence stubs",
            reopen="a recorded 1–4 rubric is accepted",
        ),
        AlgFamilyDecision(
            family_id="ALG.ACQUISITION_BUDGET",
            outcome="approved_default_tunable",
            freeze_approved=False,
            current_default=(
                f"{QUERY_BATCH_LIMIT}/{CANDIDATES_PER_BATCH}/"
                f"{STAGED_IMPORT_LIMIT}/{RECHECK_CYCLE_LIMIT}"
            ),
            reopen="production acquisition logs or a changed scholar page contract",
        ),
    )


def freeze_is_approved(family_id: str) -> bool:
    for row in alg_family_decisions():
        if row.family_id == family_id:
            return row.freeze_approved
    raise ValueError(f"unknown ALG family: {family_id}")
