from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest

import nsqd.domain.policy as policy_module
from nsqd.app.handlers import NsqdHandlerContext
from nsqd.app.use_cases import (
    ArchiveInsertUseCase,
    DivergeUseCase,
    GroundUseCase,
    MapSnapshotUseCase,
    RankArchiveUseCase,
)
from nsqd.domain.descriptor import finance_pack_universe
from nsqd.domain.policy import (
    FINANCE_POLICY,
    OPTIMIZATION_POLICY,
    IncompatibleDvalRubric,
    UnknownDomainPolicy,
    archive_cell_key,
    get_policy,
    records_for_policy,
    require_domain_policy_id,
    verdict_key,
)
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

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
POLICY_FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd" / "policies"
)
FINANCE_CELL_ID = "mechanism=flow-driven|target=drawdown|horizon=intraday"
OPTIMIZATION_CELL_ID = (
    "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"
)


def _ctx() -> NsqdHandlerContext:
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
    )


def _policy_fixture(name: str) -> dict[str, object]:
    data = tomllib.loads((POLICY_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_missing_policy_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        require_domain_policy_id({})
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        require_domain_policy_id({"domain_pack": "finance/1"})
    with pytest.raises(UnknownDomainPolicy, match="unknown domain_policy_id"):
        get_policy("not-a-pack")


def test_finance_universe_matches_descriptor_cartesian_product() -> None:
    finance = get_policy("finance/1")
    assert finance.universe() == finance_pack_universe()
    assert finance.expected_cells == frozenset({FINANCE_CELL_ID})
    assert finance.recall_probes == (("gamma-fragility", "doi:10.2139/ssrn.3725454", "paper"),)
    assert finance.required_record_types == {"paper": 1, "code": 0, "benchmark": 0}
    assert finance.min_records == 1
    assert len(get_policy("optimization/1").universe()) == 8


def test_policy_fixture_parity_with_registered_policies() -> None:
    for fixture_name, policy in (
        ("finance-1.toml", FINANCE_POLICY),
        ("optimization-1.toml", OPTIMIZATION_POLICY),
    ):
        fixture = _policy_fixture(fixture_name)
        assert fixture["policy_id"] == policy.policy_id
        assert set(fixture["dval_rubric_ids"]) == policy.dval_rubric_ids
        assert fixture["min_records"] == policy.min_records
        assert set(fixture["expected_cells"]) == policy.expected_cells
        assert fixture["required_record_types"] == policy.required_record_types
        assert fixture["recall_probes"] == [list(probe) for probe in policy.recall_probes]
        axes = fixture["axes"]
        assert isinstance(axes, dict)
        assert tuple((name, frozenset(axes[name])) for name, _ in policy.axes) == policy.axes


def test_registered_policies_are_structurally_immutable() -> None:
    assert isinstance(FINANCE_POLICY.required_record_types, MappingProxyType)
    assert isinstance(OPTIMIZATION_POLICY.required_record_types, MappingProxyType)
    assert isinstance(policy_module.POLICIES, MappingProxyType)
    with pytest.raises(TypeError):
        FINANCE_POLICY.required_record_types["paper"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        policy_module.POLICIES["new/1"] = FINANCE_POLICY  # type: ignore[index]


def test_incompatible_dval_rubric_is_rejected() -> None:
    policy = get_policy("finance/1")
    with pytest.raises(IncompatibleDvalRubric, match="incompatible dval rubric"):
        from nsqd.domain.policy import require_compatible_dval_rubric

        require_compatible_dval_rubric({"dval": {"rubric_id": "optimization-dval/1"}}, policy)


def test_same_snapshot_has_independent_verdict_keys() -> None:
    snap = "snap-shared"
    assert verdict_key(snapshot_id=snap, domain_policy_id="finance/1") == (snap, "finance/1")
    assert verdict_key(snapshot_id=snap, domain_policy_id="optimization/1") == (
        snap,
        "optimization/1",
    )
    assert verdict_key(snapshot_id=snap, domain_policy_id="finance/1") != verdict_key(
        snapshot_id=snap, domain_policy_id="optimization/1"
    )


def test_corpus_filter_excludes_other_policy_records() -> None:
    rows = [
        {"record_id": "fin", "domain_policy_id": "finance/1", "source": "doi:10.1/fin"},
        {"record_id": "opt", "domain_policy_id": "optimization/1", "source": "doi:10.1/opt"},
        {"record_id": "bare", "source": "doi:10.1/fin"},
    ]
    assert [row["record_id"] for row in records_for_policy(rows, "finance/1")] == ["fin"]
    assert [row["record_id"] for row in records_for_policy(rows, "optimization/1")] == ["opt"]


def test_score_requires_explicit_policy_and_rejects_unknown() -> None:
    ctx = _ctx()
    sid = "snap"
    ctx.snapshots.commit(sid, [], schema_version=1)
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
            candidate={
                "title": "x",
                "research_descriptor": {
                    "mechanism": "flow-driven",
                    "target": "drawdown",
                    "horizon": "intraday",
                },
            },
            axiom="a",
            generator_run_id="gen-1",
        )


def test_grounding_ignores_cross_policy_records() -> None:
    ctx = _ctx()
    sid = "snap-mix"
    ctx.snapshots.commit(sid, ["fin", "opt"], schema_version=1)
    ctx.records.put(
        {
            "record_id": "fin",
            "source": "doi:10.1/shared",
            "type": "paper",
            "tags": ["terminology"],
            "domain_policy_id": "finance/1",
        }
    )
    ctx.records.put(
        {
            "record_id": "opt",
            "source": "doi:10.1/other",
            "type": "code",
            "tags": ["terminology"],
            "domain_policy_id": "optimization/1",
        }
    )
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate={
            "title": "opt-cand",
            "domain_policy_id": "optimization/1",
            "source": "doi:10.1/shared",
            "research_descriptor": {
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
        },
        axiom="a",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id=sid, corpus_version=1)
    assert grounding["grounding_class"] != "already_done"


def test_foreign_policy_neighbors_cannot_displace_policy_scoped_evidence() -> None:
    ctx = _ctx()
    sid = "snap-vector-mix"
    finance_ids = [f"fin-{index}" for index in range(6)]
    ctx.snapshots.commit(sid, [*finance_ids, "opt"], schema_version=1)
    for record_id in finance_ids:
        ctx.records.put(
            {
                "record_id": record_id,
                "source": f"doi:10.1/{record_id}",
                "type": "paper",
                "domain_policy_id": "finance/1",
            }
        )
        ctx.index.upsert(sid, record_id, [1.0, 0.0])
    ctx.records.put(
        {
            "record_id": "opt",
            "source": "doi:10.1/opt",
            "type": "paper",
            "domain_policy_id": "optimization/1",
        }
    )
    ctx.index.upsert(sid, "opt", [0.0, 1.0])
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate={
            "title": "opt-cand",
            "domain_policy_id": "optimization/1",
            "query_vector": [1.0, 0.0],
            "research_descriptor": {
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
        },
        axiom="a",
        generator_run_id="gen-1",
    )

    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id=sid, corpus_version=1)

    assert grounding["evidence"] == pytest.approx(1.0)
    assert grounding["grounding_class"] == "orthogonal"


def test_rank_denominator_is_policy_scoped() -> None:
    opt_universe = OPTIMIZATION_POLICY.universe()
    finance = RankArchiveUseCase(
        cell_statuses={},
        domain_policy_id="finance/1",
    )
    with pytest.raises(ValueError, match="outside the descriptor universe"):
        finance.run(elite_cell_ids=set(opt_universe))
    allowed = RankArchiveUseCase(
        cell_statuses={},
        domain_policy_id="optimization/1",
    ).run(elite_cell_ids=set(opt_universe))
    assert allowed["elite_count"] == 8
    assert allowed["eligible_universe"] == 8
    assert allowed["coverage"] == 1.0


def test_rank_use_case_rejects_unknown_policy() -> None:
    with pytest.raises(UnknownDomainPolicy, match="unknown domain_policy_id"):
        RankArchiveUseCase(cell_statuses={}, domain_policy_id="missing/1").run(elite_cell_ids=set())


def test_elites_are_isolated_by_policy_scoped_archive_key() -> None:
    ctx = _ctx()
    finance_card = {
        "card_id": "fin-card",
        "domain_policy_id": "finance/1",
        "cell_id": FINANCE_CELL_ID,
        "archive_cell_key": archive_cell_key(
            domain_policy_id="finance/1",
            cell_id=FINANCE_CELL_ID,
        ),
        "title": "finance",
        "generating_operator": "A",
        "snapshot_id": "snap",
        "corpus_version": 1,
        "viability": 9,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "fin-hash",
        "card_decision": "accepted",
    }
    optimization_card = {
        **finance_card,
        "card_id": "opt-card",
        "domain_policy_id": "optimization/1",
        "cell_id": OPTIMIZATION_CELL_ID,
        "archive_cell_key": archive_cell_key(
            domain_policy_id="optimization/1",
            cell_id=OPTIMIZATION_CELL_ID,
        ),
        "candidate_artifact_hash": "opt-hash",
        "title": "optimization",
    }

    ctx.cards.put_card(finance_card)
    ctx.cards.put_card(optimization_card)
    ArchiveInsertUseCase(cards=ctx.cards).run(finance_card)
    ArchiveInsertUseCase(cards=ctx.cards).run(optimization_card)

    assert ctx.cards.elite_for_cell(finance_card["archive_cell_key"]) == finance_card
    assert ctx.cards.elite_for_cell(optimization_card["archive_cell_key"]) == optimization_card


def test_archive_insert_rejects_tampered_archive_key() -> None:
    ctx = _ctx()
    card = {
        "card_id": "fin-card",
        "domain_policy_id": "finance/1",
        "cell_id": FINANCE_CELL_ID,
        "archive_cell_key": "finance/1::tampered",
        "title": "finance",
        "generating_operator": "A",
        "snapshot_id": "snap",
        "corpus_version": 1,
        "viability": 9,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "fin-hash",
        "card_decision": "accepted",
    }

    with pytest.raises(
        ValueError, match="archive_cell_key does not match the policy-scoped cell key"
    ):
        ArchiveInsertUseCase(cards=ctx.cards).run(card)


def test_archive_insert_rejects_off_policy_cell_id() -> None:
    ctx = _ctx()
    card = {
        "card_id": "bad-card",
        "domain_policy_id": "finance/1",
        "cell_id": OPTIMIZATION_CELL_ID,
        "archive_cell_key": archive_cell_key(
            domain_policy_id="finance/1",
            cell_id=OPTIMIZATION_CELL_ID,
        ),
        "title": "bad",
        "generating_operator": "A",
        "snapshot_id": "snap",
        "corpus_version": 1,
        "viability": 9,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "bad-hash",
        "card_decision": "accepted",
    }

    with pytest.raises(ValueError, match="cell_id is outside the registered policy universe"):
        ArchiveInsertUseCase(cards=ctx.cards).run(card)


def test_archive_insert_rejects_missing_policy_and_key_even_for_finance_shaped_card() -> None:
    ctx = _ctx()
    card = {
        "card_id": "legacy-like",
        "cell_id": FINANCE_CELL_ID,
        "title": "finance",
        "generating_operator": "A",
        "snapshot_id": "snap",
        "corpus_version": 1,
        "viability": 9,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "legacy-like-hash",
        "card_decision": "accepted",
    }

    with pytest.raises(ValueError, match="domain_policy_id is required"):
        ArchiveInsertUseCase(cards=ctx.cards).run(card)


def test_map_status_table_is_policy_scoped() -> None:
    ctx = _ctx()
    ctx.records.put(
        {
            "record_id": "fin",
            "type": "paper",
            "domain_policy_id": "finance/1",
            "coordinates": {
                "mechanism": "flow-driven",
                "target": "drawdown",
                "horizon": "intraday",
            },
            "harvested_at": AS_OF,
        }
    )
    ctx.records.put(
        {
            "record_id": "opt",
            "type": "paper",
            "domain_policy_id": "optimization/1",
            "coordinates": {
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
            "harvested_at": AS_OF,
        }
    )
    ctx.snapshots.commit("snap", ["fin", "opt"], schema_version=1)
    mapped = MapSnapshotUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        morph=ctx.morph,
        clock=ctx.clock,
    )
    finance = mapped.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        snapshot_state="calibration",
    )["cell_statuses"]
    optimization = mapped.run(
        snapshot_id="snap",
        domain_policy_id="optimization/1",
        snapshot_state="calibration",
    )["cell_statuses"]
    assert len(finance) == 336
    assert len(optimization) == 8
    assert finance[FINANCE_CELL_ID] == "Code-gap"
    assert OPTIMIZATION_CELL_ID not in finance
    assert optimization[OPTIMIZATION_CELL_ID] == "Code-gap"
    assert FINANCE_CELL_ID not in optimization
    assert set(finance) == FINANCE_POLICY.universe()
    assert set(optimization) == OPTIMIZATION_POLICY.universe()
