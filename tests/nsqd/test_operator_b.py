from __future__ import annotations

from pathlib import Path

import pytest

from nsqd.app.handlers import NsqdHandlerContext, handle_diverge
from nsqd.app.use_cases import DivergeUseCase
from nsqd.composition import build_container
from nsqd.domain.diverge import (
    DEFAULT_ENABLED_OPERATORS,
    PREFERRED_TARGET_STATUSES,
    require_enabled_operators,
    require_no_axiom_inversion,
    require_operator_a,
    require_operator_b_target,
    whitespace_cells,
)
from nsqd.domain.policy import FINANCE_POLICY
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullFrontierCardStore,
    NullHarvestStore,
    NullMorphospaceStore,
    NullNsqdCandidateStore,
)
from nsqd.ports import NsqdJob
from tests.nsqd.test_operator_a import (
    AS_OF,
    MATURE,
    MISSING,
    SPARSE,
    STALLED,
    UNKNOWN,
    _finance_statuses,
)

ENABLED_OPERATORS = frozenset({"A", "B"})
MISSING_DESCRIPTOR = {
    "mechanism": "behavioral",
    "target": "returns",
    "horizon": "daily",
}


def _candidate(**overrides: object) -> dict[str, object]:
    candidate: dict[str, object] = {
        "title": "occupy archive whitespace",
        "domain_policy_id": "finance/1",
        "research_descriptor": MISSING_DESCRIPTOR,
    }
    candidate.update(overrides)
    return candidate


def _enabled_use_case(*, candidates: NullNsqdCandidateStore | None = None) -> DivergeUseCase:
    return DivergeUseCase(
        candidates=candidates or NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        clock=FixedClock(AS_OF),
        enabled_operators=ENABLED_OPERATORS,
    )


def _handler_context(*, enabled_operators: frozenset[str]) -> NsqdHandlerContext:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    return NsqdHandlerContext(
        clock=FixedClock(AS_OF),
        candidates=NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        snapshots=snapshots,
        records=records,
        harvest=NullHarvestStore(records, snapshots),
        index=NullCorpusIndex(),
        morph=NullMorphospaceStore(),
        enabled_operators=enabled_operators,
    )


def _operator_b_job() -> NsqdJob:
    return NsqdJob(
        job_id="job-b",
        type="diverge",
        status="running",
        payload={
            "candidate": _candidate(),
            "generator_run_id": "gen-b",
            "axioms": [{"statement": "occupy whitespace", "cell_id": MISSING}],
            "operator": "B",
            "target_cell_id": MISSING,
            "cell_statuses": _finance_statuses({MISSING: "Missing"}),
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )


def test_whitespace_cells_are_preferred_statuses_without_elites() -> None:
    statuses = {
        MISSING: "Missing",
        SPARSE: "Sparse",
        STALLED: "Stalled",
        MATURE: "Mature",
        UNKNOWN: "Unknown",
    }
    assert set(PREFERRED_TARGET_STATUSES) == {
        "Missing",
        "Sparse",
        "Code-gap",
        "Benchmark-gap",
        "Stalled",
    }
    assert whitespace_cells(statuses, elite_viability={SPARSE: 2}) == (MISSING, STALLED)


def test_operator_b_target_must_match_alg_sel_whitespace() -> None:
    statuses = _finance_statuses({MISSING: "Missing", SPARSE: "Sparse", MATURE: "Mature"})
    assert require_operator_b_target(MISSING, statuses) == MISSING
    with pytest.raises(ValueError, match="Operator B target must match ALG-SEL"):
        require_operator_b_target(SPARSE, statuses)
    with pytest.raises(ValueError, match="Operator B target must match ALG-SEL"):
        require_operator_b_target(MATURE, statuses, elite_viability={MATURE: 9})


def test_operator_b_fallback_uses_alg_sel_when_whitespace_is_gone() -> None:
    statuses = _finance_statuses({MATURE: "Mature", UNKNOWN: "Active"})
    elites = {MATURE: 12, UNKNOWN: 4}
    assert require_operator_b_target(UNKNOWN, statuses, elite_viability=elites) == UNKNOWN
    with pytest.raises(ValueError, match="Operator B target must match ALG-SEL"):
        require_operator_b_target(MATURE, statuses, elite_viability=elites)


def test_operator_b_forbids_axiom_inversion() -> None:
    require_no_axiom_inversion(
        candidate={"title": "occupy missing cell", "inversion": False},
        axioms=[{"statement": "liquidity is not alpha", "cell_id": MISSING}],
    )
    with pytest.raises(ValueError, match="Operator B cannot invert axioms"):
        require_no_axiom_inversion(candidate={"inversion": True}, axioms=[])
    with pytest.raises(ValueError, match="Operator B cannot invert axioms"):
        require_no_axiom_inversion(
            candidate={},
            axioms=[{"statement": "x", "inverted": True}],
        )


def test_default_composition_rejects_operator_b() -> None:
    statuses = _finance_statuses({MISSING: "Missing"})
    with pytest.raises(ValueError, match="baseline requires Operator A"):
        require_operator_a("B")
    with pytest.raises(ValueError, match="not enabled by composition"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=NullFrontierCardStore(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-b",
            axioms=[{"statement": "occupy whitespace", "cell_id": MISSING}],
            operator="B",
            target_cell_id=MISSING,
            cell_statuses=statuses,
        )
    assert MISSING in FINANCE_POLICY.universe()


def test_allowlisted_diverge_persists_operator_b_with_target_provenance() -> None:
    candidates = NullNsqdCandidateStore()
    digest = _enabled_use_case(candidates=candidates).run(
        candidate=_candidate(),
        generator_run_id="gen-b",
        axioms=[{"statement": "occupy whitespace", "cell_id": MISSING}],
        operator="B",
        target_cell_id=MISSING,
        cell_statuses=_finance_statuses({MISSING: "Missing"}),
    )

    stored = candidates.get_artifact(digest)
    assert stored is not None
    assert stored["operator"] == "B"
    assert stored["target_cell_id"] == MISSING
    assert stored["axioms"] == [{"statement": "occupy whitespace", "cell_id": MISSING}]


@pytest.mark.parametrize(
    ("candidate", "axioms", "message"),
    [
        (
            _candidate(
                research_descriptor={
                    "mechanism": "flow-driven",
                    "target": "drawdown",
                    "horizon": "intraday",
                }
            ),
            [{"statement": "occupy whitespace", "cell_id": MISSING}],
            "research_descriptor must resolve to the Operator B target",
        ),
        (
            _candidate(),
            [{"statement": "general context"}],
            "Operator B requires a target-bound axiom",
        ),
        (
            _candidate(inversion=True),
            [{"statement": "occupy whitespace", "cell_id": MISSING}],
            "Operator B cannot invert axioms",
        ),
    ],
)
def test_allowlisted_diverge_requires_operator_b_occupancy_proof(
    candidate: dict[str, object],
    axioms: list[dict[str, object]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _enabled_use_case().run(
            candidate=candidate,
            generator_run_id="gen-b",
            axioms=axioms,
            operator="B",
            target_cell_id=MISSING,
            cell_statuses=_finance_statuses({MISSING: "Missing"}),
        )


def test_operator_b_conflicts_with_same_candidate_persisted_by_operator_a() -> None:
    candidates = NullNsqdCandidateStore()
    use_case = _enabled_use_case(candidates=candidates)
    statuses = _finance_statuses({MISSING: "Missing"})
    candidate = _candidate()
    axioms = [{"statement": "occupy whitespace", "cell_id": MISSING}]
    use_case.run(
        candidate=candidate,
        generator_run_id="gen-a",
        axioms=axioms,
        operator="A",
        target_cell_id=MISSING,
        cell_statuses=statuses,
    )

    with pytest.raises(ValueError, match="immutable artifact conflict"):
        use_case.run(
            candidate=candidate,
            generator_run_id="gen-b",
            axioms=axioms,
            operator="B",
            target_cell_id=MISSING,
            cell_statuses=statuses,
        )


def test_handler_job_cannot_widen_composition_allowlist() -> None:
    default_ctx = _handler_context(enabled_operators=frozenset({"A"}))
    with pytest.raises(ValueError, match="not enabled by composition"):
        handle_diverge(default_ctx, _operator_b_job())

    enabled_ctx = _handler_context(enabled_operators=ENABLED_OPERATORS)
    result = handle_diverge(enabled_ctx, _operator_b_job())
    stored = enabled_ctx.candidates.get_artifact(result["candidate_artifact_hash"])
    assert stored is not None
    assert stored["operator"] == "B"


def test_container_defaults_to_a_and_can_explicitly_allowlist_b(tmp_path: Path) -> None:
    default_container = build_container(
        db_path=tmp_path / "default.sqlite",
        index_path=tmp_path / "default-index",
    )
    assert default_container.ctx.enabled_operators == frozenset({"A"})
    assert default_container.ctx.novelty_threshold_tau == 0.45

    enabled_container = build_container(
        db_path=tmp_path / "enabled.sqlite",
        index_path=tmp_path / "enabled-index",
        enabled_operators=ENABLED_OPERATORS,
    )
    assert enabled_container.ctx.enabled_operators == ENABLED_OPERATORS


def test_require_enabled_operators_allows_a_or_a_and_b() -> None:
    assert require_enabled_operators(None) == frozenset({"A"})
    assert require_enabled_operators(DEFAULT_ENABLED_OPERATORS) == frozenset({"A"})
    assert require_enabled_operators(["B", "A", "A"]) == frozenset({"A", "B"})
    with pytest.raises(ValueError, match="must include Operator A"):
        require_enabled_operators({"B"})
    with pytest.raises(ValueError, match="operator C is not supported"):
        require_enabled_operators({"A", "C"})
    with pytest.raises(ValueError, match="unknown operator"):
        require_enabled_operators({"A", "H"})
    with pytest.raises(ValueError, match="must include Operator A"):
        require_enabled_operators([])
    for scalar in ("A", "AB", "B", b"AB", {"A": True, "B": True}):
        with pytest.raises(ValueError, match="must be an iterable of operator ids"):
            require_enabled_operators(scalar)


def test_build_container_rejects_deferred_operator_in_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="operator C is not supported"):
        build_container(
            db_path=tmp_path / "deferred.sqlite",
            index_path=tmp_path / "deferred-index",
            enabled_operators=frozenset({"A", "C"}),
        )
