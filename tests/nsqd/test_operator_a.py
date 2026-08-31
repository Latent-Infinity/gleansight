from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nsqd.app.handlers import handle_diverge
from nsqd.app.use_cases import DivergeUseCase, artifact_hash_for
from nsqd.domain.diverge import (
    normalize_axiom_rows,
    parent_card_id_for_target,
    require_operator_a,
    select_target_cell,
)
from nsqd.domain.policy import FINANCE_POLICY, archive_cell_key
from nsqd.domain.status import CellStatus
from nsqd.null_adapters import FixedClock, NullFrontierCardStore, NullNsqdCandidateStore
from nsqd.ports import NsqdJob

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
MISSING = "mechanism=behavioral|target=returns|horizon=daily"
SPARSE = "mechanism=flow-driven|target=drawdown|horizon=intraday"
STALLED = "mechanism=institutional|target=liquidity|horizon=weekly"
MATURE = "mechanism=reflexivity|target=crowding|horizon=tick"
UNKNOWN = "mechanism=microstructure|target=slippage|horizon=event-time"
OPT_CELL = "problem=constrained-expectation|method=first-order|setting=full-rank"


def _finance_statuses(
    overrides: dict[str, CellStatus] | None = None,
) -> dict[str, CellStatus]:
    table: dict[str, CellStatus] = {cell_id: "Unknown" for cell_id in FINANCE_POLICY.universe()}
    if overrides is not None:
        table.update(overrides)
    return table


def test_select_target_prefers_gap_cells_without_elites() -> None:
    chosen = select_target_cell(
        {
            MATURE: "Mature",
            SPARSE: "Sparse",
            MISSING: "Missing",
            STALLED: "Stalled",
        },
        elite_viability={MATURE: 9, SPARSE: 1},
    )
    assert chosen == MISSING


def test_select_target_ties_break_on_smaller_cell_id() -> None:
    chosen = select_target_cell(
        {STALLED: "Stalled", MISSING: "Missing", SPARSE: "Sparse"},
        elite_viability={},
    )
    assert chosen == MISSING
    assert chosen == sorted([STALLED, MISSING, SPARSE])[0]


def test_select_target_falls_back_to_lowest_elite_viability() -> None:
    chosen = select_target_cell(
        {MATURE: "Mature", UNKNOWN: "Active"},
        elite_viability={MATURE: 12, UNKNOWN: 4},
    )
    assert chosen == UNKNOWN


def test_select_target_equal_viability_uses_smaller_cell_id() -> None:
    chosen = select_target_cell(
        {MATURE: "Mature", UNKNOWN: "Active"},
        elite_viability={MATURE: 4, UNKNOWN: 4},
    )
    assert chosen == min(MATURE, UNKNOWN)


def test_select_target_all_unknown_without_elites_uses_smaller_cell_id() -> None:
    chosen = select_target_cell({UNKNOWN: "Unknown", MISSING: "Unknown"})
    assert chosen == min(UNKNOWN, MISSING)


def test_select_target_rejects_empty_table() -> None:
    with pytest.raises(ValueError, match="cell_statuses must not be empty"):
        select_target_cell({})


def test_require_operator_a_rejects_every_non_a_operator() -> None:
    assert require_operator_a("A") == "A"
    for operator in ("B", "C", "D", "E", "F", "G", "a", ""):
        with pytest.raises(ValueError, match="baseline requires Operator A"):
            require_operator_a(operator)


def test_operator_decisions_support_b_without_enabling_it_by_default() -> None:
    from nsqd.domain.diverge import (
        operator_decisions,
        operator_is_enabled,
    )

    rows = operator_decisions()
    assert [row.operator_id for row in rows] == ["A", "B", "C", "D", "E", "F", "G"]
    by_id = {row.operator_id: row for row in rows}
    assert by_id["A"].activation == "supported"
    assert by_id["A"].runtime_enabled is True
    assert by_id["B"].activation == "supported"
    assert by_id["B"].runtime_enabled is True
    assert operator_is_enabled("B") is False
    assert operator_is_enabled("B", enabled_operators=frozenset({"A", "B"})) is True
    assert "composition" in by_id["B"].wait_on
    for operator_id in ("C", "D", "E", "F", "G"):
        assert by_id[operator_id].activation == "deferred"
        assert by_id[operator_id].runtime_enabled is False
        assert operator_is_enabled(operator_id) is False
    assert operator_is_enabled("A") is True
    assert "separate" in by_id["E"].wait_on
    assert "activation" in by_id["E"].wait_on
    assert "axis" in by_id["F"].wait_on.lower()
    assert "failure" in by_id["G"].wait_on.lower()
    with pytest.raises(ValueError, match="unknown operator"):
        operator_is_enabled("H")


def test_executable_tau_does_not_authorize_operator_e() -> None:
    from nsqd.domain.diverge import require_operator
    from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU

    assert NOVELTY_THRESHOLD_TAU == 0.45
    with pytest.raises(ValueError, match="operator E is not supported"):
        require_operator("E", enabled_operators=frozenset({"A", "B"}))


def test_operator_c_wait_on_does_not_require_b_activation() -> None:
    from nsqd.domain.diverge import operator_decisions, operator_is_enabled, require_operator

    by_id = {row.operator_id: row for row in operator_decisions()}
    wait_on = by_id["C"].wait_on.lower()
    assert by_id["C"].activation == "deferred"
    assert by_id["C"].runtime_enabled is False
    assert "b is activated" not in wait_on
    assert "after b" not in wait_on
    assert "literature" in wait_on
    assert "activation" in wait_on
    assert operator_is_enabled("C", enabled_operators=frozenset({"A", "B"})) is False
    with pytest.raises(ValueError, match="operator C is not supported"):
        require_operator("C", enabled_operators=frozenset({"A", "B"}))


def test_normalize_axiom_rows_accepts_strings_and_structured_rows() -> None:
    rows = normalize_axiom_rows(
        [
            "predictors assume stationary return signal",
            {"statement": "liquidity is not alpha", "cell_id": SPARSE},
        ]
    )
    assert rows == [
        {"statement": "predictors assume stationary return signal"},
        {"statement": "liquidity is not alpha", "cell_id": SPARSE},
    ]


def test_normalize_axiom_rows_rejects_empty_or_blank() -> None:
    with pytest.raises(ValueError, match="axiom list is required"):
        normalize_axiom_rows([])
    with pytest.raises(ValueError, match="axiom statement is required"):
        normalize_axiom_rows([{"statement": "  "}])
    with pytest.raises(ValueError, match="axiom statement is required"):
        normalize_axiom_rows([""])
    with pytest.raises(ValueError, match="axiom statement is required"):
        normalize_axiom_rows([{"cell_id": SPARSE}])
    with pytest.raises(ValueError, match="cell_id must be a non-empty string"):
        normalize_axiom_rows([{"statement": "x", "cell_id": 7}])


def _card(card_id: str, cell_id: str, viability: object) -> dict[str, object]:
    return {
        "card_id": card_id,
        "domain_policy_id": "finance/1",
        "cell_id": cell_id,
        "archive_cell_key": archive_cell_key(domain_policy_id="finance/1", cell_id=cell_id),
        "viability": viability,
    }


def _cards() -> NullFrontierCardStore:
    return NullFrontierCardStore()


def test_empty_target_cell_has_no_parent_card() -> None:
    assert parent_card_id_for_target(elite_card_id=None, parent_card_id=None) is None
    with pytest.raises(ValueError, match="empty target cell has no parent card"):
        parent_card_id_for_target(elite_card_id=None, parent_card_id="card-1")


def test_parent_card_must_be_the_target_elite() -> None:
    assert parent_card_id_for_target(elite_card_id="elite-1", parent_card_id=None) is None
    assert parent_card_id_for_target(elite_card_id="elite-1", parent_card_id="elite-1") == "elite-1"
    with pytest.raises(ValueError, match="parent_card_id must be the target cell elite"):
        parent_card_id_for_target(elite_card_id="elite-1", parent_card_id="other")


def test_diverge_persists_axiom_list_and_operator_a() -> None:
    candidates = NullNsqdCandidateStore()
    digest = DivergeUseCase(
        candidates=candidates,
        cards=_cards(),
        clock=FixedClock(AS_OF),
    ).run(
        candidate={"title": "x", "domain_policy_id": "finance/1"},
        generator_run_id="gen-1",
        axioms=["first axiom", {"statement": "second axiom"}],
    )
    stored = candidates.get_artifact(digest)
    assert stored is not None
    assert stored["operator"] == "A"
    assert stored["axiom"] == "first axiom"
    assert stored["axioms"] == [
        {"statement": "first axiom"},
        {"statement": "second axiom"},
    ]
    assert stored["parent_card_id"] is None
    assert stored["target_cell_id"] is None


def test_diverge_rejects_caller_target_without_status_table() -> None:
    with pytest.raises(ValueError, match="cell_statuses are required"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=_cards(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            target_cell_id=MISSING,
        )


def test_diverge_rejects_operator_b_and_parent_on_empty_cell() -> None:
    use_case = DivergeUseCase(
        candidates=NullNsqdCandidateStore(),
        cards=_cards(),
        clock=FixedClock(AS_OF),
    )
    candidate = {"title": "x", "domain_policy_id": "finance/1"}
    with pytest.raises(ValueError, match="not enabled by composition"):
        use_case.run(
            candidate=candidate,
            generator_run_id="gen-1",
            axiom="an axiom",
            operator="B",
        )
    with pytest.raises(ValueError, match="empty target cell has no parent card"):
        use_case.run(
            candidate=candidate,
            generator_run_id="gen-1",
            axiom="an axiom",
            parent_card_id="elite-1",
        )


def test_diverge_selects_target_from_status_table_and_actual_elite() -> None:
    candidates = NullNsqdCandidateStore()
    cards = _cards()
    cards.put_card(_card("elite-sparse", SPARSE, 2))
    cards.put_card(_card("elite-mature", MATURE, 8))
    cards.set_elite(archive_cell_key(domain_policy_id="finance/1", cell_id=SPARSE), "elite-sparse")
    cards.set_elite(archive_cell_key(domain_policy_id="finance/1", cell_id=MATURE), "elite-mature")

    digest = DivergeUseCase(
        candidates=candidates,
        cards=cards,
        clock=FixedClock(AS_OF),
    ).run(
        candidate={"title": "x", "domain_policy_id": "finance/1"},
        generator_run_id="gen-1",
        axioms=["first axiom"],
        cell_statuses=_finance_statuses({MATURE: "Mature", SPARSE: "Sparse"}),
        parent_card_id="elite-sparse",
    )

    stored = candidates.get_artifact(digest)
    assert stored is not None
    assert stored["target_cell_id"] == SPARSE
    assert stored["parent_card_id"] == "elite-sparse"


def test_diverge_rejects_cross_policy_cells_in_status_table() -> None:
    with pytest.raises(ValueError, match="outside the registered policy universe"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=_cards(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            cell_statuses={OPT_CELL: "Missing"},
        )


def test_diverge_requires_complete_policy_universe_when_status_table_is_supplied() -> None:
    with pytest.raises(ValueError, match="cell_statuses must match the selected policy universe"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=_cards(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            cell_statuses={SPARSE: "Sparse"},
        )


def test_diverge_rejects_invalid_cell_status_values() -> None:
    universe = FINANCE_POLICY.universe()
    with pytest.raises(ValueError, match="invalid CellStatus value"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=_cards(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            cell_statuses={
                cell_id: ("Bogus" if cell_id == SPARSE else "Unknown") for cell_id in universe
            },
        )


def test_diverge_rejects_axiom_cells_outside_policy_or_target() -> None:
    use_case = DivergeUseCase(
        candidates=NullNsqdCandidateStore(),
        cards=_cards(),
        clock=FixedClock(AS_OF),
    )
    candidate = {"title": "x", "domain_policy_id": "finance/1"}
    with pytest.raises(ValueError, match="axiom cell is outside"):
        use_case.run(
            candidate=candidate,
            generator_run_id="gen-1",
            axioms=[
                {
                    "statement": "first axiom",
                    "cell_id": OPT_CELL,
                }
            ],
            cell_statuses=_finance_statuses({SPARSE: "Sparse"}),
        )
    with pytest.raises(ValueError, match="axiom cell_id must match"):
        use_case.run(
            candidate=candidate,
            generator_run_id="gen-1",
            axioms=[{"statement": "first axiom", "cell_id": MATURE}],
            cell_statuses=_finance_statuses({SPARSE: "Sparse"}),
        )


def test_diverge_rejects_target_outside_policy_universe() -> None:
    with pytest.raises(ValueError, match="outside the registered policy universe"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=_cards(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            target_cell_id=OPT_CELL,
        )


def test_diverge_rejects_caller_target_that_disagrees_with_alg_sel() -> None:
    with pytest.raises(ValueError, match="target_cell_id disagrees with ALG-SEL"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=_cards(),
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            target_cell_id=MATURE,
            cell_statuses=_finance_statuses({MATURE: "Mature", SPARSE: "Sparse"}),
        )


@pytest.mark.parametrize("viability", [True, False, -1, 26, 3.5, "7"])
def test_diverge_rejects_invalid_elite_viability_values(viability: object) -> None:
    cards = _cards()
    cards.put_card(_card("elite-sparse", SPARSE, viability))
    cards.set_elite(archive_cell_key(domain_policy_id="finance/1", cell_id=SPARSE), "elite-sparse")
    with pytest.raises(ValueError, match="elite viability must be a non-bool int in 0..25"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=cards,
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            cell_statuses=_finance_statuses({SPARSE: "Mature"}),
        )


def test_diverge_rejects_parent_card_that_is_not_the_actual_target_elite() -> None:
    cards = _cards()
    cards.put_card(_card("elite-sparse", SPARSE, 2))
    cards.set_elite(archive_cell_key(domain_policy_id="finance/1", cell_id=SPARSE), "elite-sparse")
    with pytest.raises(ValueError, match="parent_card_id must be the target cell elite"):
        DivergeUseCase(
            candidates=NullNsqdCandidateStore(),
            cards=cards,
            clock=FixedClock(AS_OF),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-1",
            axioms=["first axiom"],
            cell_statuses=_finance_statuses({SPARSE: "Sparse"}),
            parent_card_id="other-card",
        )


def test_diverge_same_semantic_inputs_are_idempotent_across_generated_at() -> None:
    candidates = NullNsqdCandidateStore()
    cards = _cards()
    first = DivergeUseCase(candidates=candidates, cards=cards, clock=FixedClock(AS_OF)).run(
        candidate={"title": "x", "domain_policy_id": "finance/1"},
        generator_run_id="gen-1",
        axioms=["first axiom"],
    )
    second = DivergeUseCase(
        candidates=candidates,
        cards=cards,
        clock=FixedClock(datetime(2024, 1, 2, tzinfo=UTC)),
    ).run(
        candidate={"title": "x", "domain_policy_id": "finance/1"},
        generator_run_id="gen-1",
        axioms=["first axiom"],
    )
    stored = candidates.get_artifact(first)
    assert first == second
    assert stored is not None
    assert stored["generated_at"] == AS_OF.isoformat()


def test_diverge_rejects_immutable_artifact_conflicts() -> None:
    candidates = NullNsqdCandidateStore()
    cards = _cards()
    DivergeUseCase(candidates=candidates, cards=cards, clock=FixedClock(AS_OF)).run(
        candidate={"title": "x", "domain_policy_id": "finance/1"},
        generator_run_id="gen-1",
        axioms=["first axiom"],
    )
    with pytest.raises(ValueError, match="immutable artifact conflict"):
        DivergeUseCase(
            candidates=candidates,
            cards=cards,
            clock=FixedClock(datetime(2024, 1, 2, tzinfo=UTC)),
        ).run(
            candidate={"title": "x", "domain_policy_id": "finance/1"},
            generator_run_id="gen-2",
            axioms=["different axiom"],
        )


def test_diverge_treats_legacy_operator_a_artifact_as_idempotent() -> None:
    candidate = {"title": "x", "domain_policy_id": "finance/1"}
    digest = artifact_hash_for(candidate)
    candidates = NullNsqdCandidateStore()
    candidates.put_artifact(
        digest,
        {
            "candidate": candidate,
            "axiom": "first axiom",
            "generator_run_id": "gen-1",
            "generated_at": AS_OF.isoformat(),
        },
    )

    replayed = DivergeUseCase(
        candidates=candidates,
        cards=_cards(),
        clock=FixedClock(datetime(2024, 1, 2, tzinfo=UTC)),
    ).run(
        candidate=candidate,
        generator_run_id="gen-1",
        axioms=["first axiom"],
    )

    assert replayed == digest
    stored = candidates.get_artifact(digest)
    assert stored is not None
    assert "axioms" not in stored


def test_handler_accepts_axiom_list_payload() -> None:
    from nsqd.app.handlers import NsqdHandlerContext
    from nsqd.null_adapters import (
        NullCorpusIndex,
        NullCorpusRecordStore,
        NullCorpusSnapshotStore,
        NullFrontierCardStore,
        NullHarvestStore,
        NullMorphospaceStore,
    )

    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    ctx = NsqdHandlerContext(
        clock=FixedClock(AS_OF),
        candidates=NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        snapshots=snapshots,
        records=records,
        harvest=NullHarvestStore(records, snapshots),
        index=NullCorpusIndex(),
        morph=NullMorphospaceStore(),
    )
    job = NsqdJob(
        job_id="j1",
        type="diverge",
        status="running",
        payload={
            "candidate": {"title": "x", "domain_policy_id": "finance/1"},
            "axioms": ["predictors assume stationary return signal"],
            "generator_run_id": "gen-1",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    result = handle_diverge(ctx, job)
    stored = ctx.candidates.get_artifact(result["candidate_artifact_hash"])
    assert stored is not None
    assert stored["operator"] == "A"
    assert stored["axioms"] == [{"statement": "predictors assume stationary return signal"}]


def test_handler_rejects_non_list_axioms_payload() -> None:
    from nsqd.app.handlers import NsqdHandlerContext
    from nsqd.null_adapters import (
        NullCorpusIndex,
        NullCorpusRecordStore,
        NullCorpusSnapshotStore,
        NullHarvestStore,
        NullMorphospaceStore,
    )

    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    ctx = NsqdHandlerContext(
        clock=FixedClock(AS_OF),
        candidates=NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        snapshots=snapshots,
        records=records,
        harvest=NullHarvestStore(records, snapshots),
        index=NullCorpusIndex(),
        morph=NullMorphospaceStore(),
    )
    job = NsqdJob(
        job_id="j1",
        type="diverge",
        status="running",
        payload={
            "candidate": {"title": "x", "domain_policy_id": "finance/1"},
            "axioms": "predictors assume stationary return signal",
            "generator_run_id": "gen-1",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(ValueError, match="axioms must be a list"):
        handle_diverge(ctx, job)


def test_handler_rejects_present_non_dict_cell_statuses_payload() -> None:
    from nsqd.app.handlers import NsqdHandlerContext
    from nsqd.null_adapters import (
        NullCorpusIndex,
        NullCorpusRecordStore,
        NullCorpusSnapshotStore,
        NullHarvestStore,
        NullMorphospaceStore,
    )

    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    ctx = NsqdHandlerContext(
        clock=FixedClock(AS_OF),
        candidates=NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        snapshots=snapshots,
        records=records,
        harvest=NullHarvestStore(records, snapshots),
        index=NullCorpusIndex(),
        morph=NullMorphospaceStore(),
    )
    job = NsqdJob(
        job_id="j1",
        type="diverge",
        status="running",
        payload={
            "candidate": {"title": "x", "domain_policy_id": "finance/1"},
            "axioms": ["predictors assume stationary return signal"],
            "generator_run_id": "gen-1",
            "cell_statuses": [SPARSE],
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(ValueError, match="cell_statuses must be a mapping"):
        handle_diverge(ctx, job)
