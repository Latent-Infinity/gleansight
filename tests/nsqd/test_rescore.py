from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nsqd.app.handlers import NsqdHandlerContext, handle_rescore
from nsqd.app.use_cases import (
    ArchiveInsertUseCase,
    DivergeUseCase,
    GroundUseCase,
    HarvestUseCase,
    RescoreUseCase,
    ScoreUseCase,
)
from nsqd.composition import build_container
from nsqd.domain.card import needs_re_score
from nsqd.null_adapters import (
    FixedClock,
    HashParaphraseEmbedder,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullFrontierCardStore,
    NullHarvestStore,
    NullMorphospaceStore,
    NullNsqdCandidateStore,
)
from nsqd.ports import NsqdJob
from nsqd.runner import run_job

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"


class _HybridSearch:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.calls: list[tuple[str, int]] = []
        self._hits = hits

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((query, limit))
        return list(self._hits)


def _ctx(
    *,
    scholar: object | None = None,
    hybrid: object | None = None,
) -> NsqdHandlerContext:
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
        scholar_client=scholar,
        paper_vector_index=hybrid,
    )


def _rescore(ctx: NsqdHandlerContext) -> RescoreUseCase:
    return RescoreUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        cards=ctx.cards,
        live_search=ctx.scholar_client,
        hybrid_search=ctx.paper_vector_index,
    )


def _candidate() -> dict[str, object]:
    return {
        "title": "gamma",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "flow-driven",
            "target": "drawdown",
            "horizon": "intraday",
        },
        "mechanism": "flow",
        "inefficiency": "x",
        "counterparty": "y",
        "persistence": "z",
        "capacity": "c",
        "regime_dependence": "r",
        "cheapest_falsifier": "f",
        "kill_criteria": "k",
        "differential_prediction": "d",
        "dval": {
            "assigned_by": "tester",
            "rubric_id": "r1",
            "assigned_at": "2024-01-01T00:00:00+00:00",
            "value": 5,
        },
    }


def _score_on(
    ctx: NsqdHandlerContext,
    *,
    snapshot_id: str,
    corpus_version: int,
    evaluator_run_id: str,
) -> dict[str, object]:
    ctx.snapshots.commit(snapshot_id, [], schema_version=1)
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=_candidate(),
        axiom="x",
        generator_run_id="gen-1",
    )
    GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=snapshot_id,
        corpus_version=corpus_version,
    )
    scored = ScoreUseCase(
        candidates=ctx.candidates,
        cards=ctx.cards,
        snapshots=ctx.snapshots,
        records=ctx.records,
    ).run(
        candidate_artifact_hash=artifact_hash,
        evaluator_run_id=evaluator_run_id,
        snapshot_id=snapshot_id,
        corpus_version=corpus_version,
        snapshot_state="smoke_only",
    )
    ArchiveInsertUseCase(cards=ctx.cards).run(scored["card"])
    return scored


def test_needs_re_score_when_snapshot_ids_differ() -> None:
    assert needs_re_score(card_snapshot_id="snap-a", current_snapshot_id="snap-b") is True
    assert needs_re_score(card_snapshot_id="snap-a", current_snapshot_id="snap-a") is False


def test_rescore_is_noop_when_card_matches_current_snapshot() -> None:
    ctx = _ctx()
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    result = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-old",
        current_corpus_version=1,
        snapshot_state="smoke_only",
        evaluator_run_id="eval-2",
    )
    assert result["needs_re_score"] is False
    assert result["card"]["snapshot_id"] == "snap-old"
    assert result["archive"]["reason"] == "viability_zero"


def test_current_card_reconciles_interrupted_archive_cleanup() -> None:
    ctx = _ctx()
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    ctx.cards.set_elite(str(card["archive_cell_key"]), str(card["card_id"]))
    assert ctx.cards.elite_for_cell(str(card["archive_cell_key"])) is not None

    result = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-old",
        current_corpus_version=1,
        snapshot_state="smoke_only",
        evaluator_run_id="eval-retry",
    )

    assert result["needs_re_score"] is False
    assert result["archive"]["reason"] == "viability_zero"
    assert result["archive"]["elite"] is None
    assert result["elite"] is None
    assert ctx.cards.elite_for_cell(str(card["archive_cell_key"])) is None

    repeated = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-old",
        current_corpus_version=1,
        snapshot_state="smoke_only",
        evaluator_run_id="eval-retry-2",
    )
    assert repeated["archive"]["elite"] is None
    assert repeated["elite"] is None


def test_current_card_reconciles_interrupted_archive_insertion() -> None:
    ctx = _ctx()
    ctx.snapshots.commit("snap-prior", [], schema_version=1)
    assert ctx.snapshots.commit("snap-current", [], schema_version=1) == 2
    card = {
        "card_id": "current-positive",
        "domain_policy_id": "finance/1",
        "cell_id": CELL,
        "archive_cell_key": f"finance/1::{CELL}",
        "title": "positive",
        "generating_operator": "A",
        "snapshot_id": "snap-current",
        "corpus_version": 2,
        "viability": 5,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "hash-current",
        "card_decision": "accepted",
    }
    ctx.cards.put_card(card)

    result = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-current",
        current_corpus_version=2,
        snapshot_state="calibration",
        evaluator_run_id="eval-retry",
    )

    assert result["needs_re_score"] is False
    assert result["archive"]["inserted"] is True
    assert result["archive"]["elite"] == card
    assert result["elite"] == card
    assert ctx.cards.elite_for_cell(str(card["archive_cell_key"])) == card

    repeated = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-current",
        current_corpus_version=2,
        snapshot_state="calibration",
        evaluator_run_id="eval-retry-2",
    )
    assert repeated["archive"]["elite"] == card
    assert repeated["elite"] == card


def test_current_snapshot_replay_normalizes_legacy_finance_card_without_policy_fields() -> None:
    ctx = _ctx()
    ctx.snapshots.commit("snap-current", [], schema_version=1)
    legacy_card = {
        "card_id": "legacy-finance",
        "cell_id": CELL,
        "title": "legacy",
        "generating_operator": "A",
        "snapshot_id": "snap-current",
        "corpus_version": 1,
        "viability": 5,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "legacy-hash",
        "card_decision": "accepted",
    }
    ctx.cards.put_card(legacy_card)

    result = _rescore(ctx).run(
        card_id="legacy-finance",
        current_snapshot_id="snap-current",
        current_corpus_version=1,
        snapshot_state="calibration",
        evaluator_run_id="eval-retry",
    )

    normalized = result["card"]
    assert normalized["domain_policy_id"] == "finance/1"
    assert normalized["archive_cell_key"] == f"finance/1::{CELL}"
    assert result["archive"]["elite"] == normalized
    assert ctx.cards.elite_for_cell(f"finance/1::{CELL}") == normalized


def test_current_snapshot_replay_rejects_legacy_card_with_non_finance_cell() -> None:
    ctx = _ctx()
    opt_cell = "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"
    ctx.snapshots.commit("snap-current", [], schema_version=1)
    ctx.cards.put_card(
        {
            "card_id": "legacy-unknown",
            "cell_id": opt_cell,
            "title": "legacy",
            "generating_operator": "A",
            "snapshot_id": "snap-current",
            "corpus_version": 1,
            "viability": 5,
            "nov": 1,
            "mech": 5,
            "fals": 5,
            "dpred": 5,
            "dval": 5,
            "candidate_artifact_hash": "legacy-hash",
            "card_decision": "accepted",
        }
    )

    with pytest.raises(ValueError, match="legacy card requires explicit domain_policy_id"):
        _rescore(ctx).run(
            card_id="legacy-unknown",
            current_snapshot_id="snap-current",
            current_corpus_version=1,
            snapshot_state="calibration",
            evaluator_run_id="eval-retry",
        )


def test_stale_card_is_rescored_against_current_snapshot() -> None:
    ctx = _ctx()
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    ctx.snapshots.commit("snap-new", [], schema_version=1)
    result = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-new",
        current_corpus_version=2,
        snapshot_state="smoke_only",
        evaluator_run_id="eval-2",
    )
    assert result["needs_re_score"] is True
    assert result["card"]["snapshot_id"] == "snap-new"
    assert result["card"]["corpus_version"] == 2
    stored = ctx.cards.get_card(str(card["card_id"]))
    assert stored is not None
    assert stored["snapshot_id"] == "snap-new"


def test_stale_calibration_card_replays_live_grounding() -> None:
    hybrid = _HybridSearch([{"paper_id": "p1", "score": 0.75}])
    ctx = _ctx(hybrid=hybrid)
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    ctx.snapshots.commit("snap-new", [], schema_version=1)

    result = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-new",
        current_corpus_version=2,
        snapshot_state="calibration",
        evaluator_run_id="eval-2",
    )

    artifact = ctx.candidates.get_artifact(str(card["candidate_artifact_hash"]))
    assert artifact is not None
    assert artifact["grounding"]["live_call_count"] == 1
    assert artifact["grounding"]["grounding_class"] == "related_partial"
    assert artifact["novelty"]["snapshot_state"] == "calibration"
    assert result["needs_re_score"] is True
    assert hybrid.calls == [("gamma", 3)]


def test_rescore_replays_elite_and_clears_rejected_elite() -> None:
    ctx = _ctx()
    high = {
        "card_id": "c-high",
        "domain_policy_id": "finance/1",
        "cell_id": CELL,
        "archive_cell_key": f"finance/1::{CELL}",
        "title": "t",
        "generating_operator": "A",
        "snapshot_id": "snap-old",
        "corpus_version": 1,
        "viability": 9,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "hash-high",
        "card_decision": "accepted",
    }
    ctx.cards.put_card(high)
    ArchiveInsertUseCase(cards=ctx.cards).run(high)
    assert ctx.cards.elite_for_cell(str(high["archive_cell_key"])) == high

    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    ctx.cards.set_elite(str(card["archive_cell_key"]), str(card["card_id"]))
    ctx.snapshots.commit("snap-new", [], schema_version=1)
    result = _rescore(ctx).run(
        card_id=str(card["card_id"]),
        current_snapshot_id="snap-new",
        current_corpus_version=2,
        snapshot_state="smoke_only",
        evaluator_run_id="eval-2",
    )
    assert result["needs_re_score"] is True
    assert result["card"]["viability"] == 0
    assert ctx.cards.elite_for_cell(str(card["archive_cell_key"])) is None


def test_handle_rescore_job() -> None:
    hybrid = _HybridSearch([{"paper_id": "p1", "score": 0.75}])
    ctx = _ctx(hybrid=hybrid)
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    ctx.snapshots.commit("snap-new", [], schema_version=1)
    job = NsqdJob(
        job_id="jr",
        type="rescore",
        status="running",
        payload={
            "card_id": card["card_id"],
            "current_snapshot_id": "snap-new",
            "current_corpus_version": 2,
            "snapshot_state": "calibration",
            "evaluator_run_id": "payload-must-not-control-provenance",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    result = handle_rescore(ctx, job)
    assert result["status"] == "succeeded"
    assert result["needs_re_score"] is True
    assert result["card"]["snapshot_id"] == "snap-new"
    assert result["card"]["evaluator_run_id"] == "rescore:jr"
    artifact = ctx.candidates.get_artifact(str(card["candidate_artifact_hash"]))
    assert artifact is not None
    assert artifact["grounding"]["live_call_count"] == 1
    assert artifact["novelty"]["snapshot_state"] == "calibration"
    assert hybrid.calls == [("gamma", 3)]


def test_queued_rescore_dispatches_through_skeleton_runner(tmp_path: Path) -> None:
    container = build_container(
        db_path=tmp_path / "papers.db",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
    )
    scored = _score_on(
        container.ctx,
        snapshot_id="snap-old",
        corpus_version=1,
        evaluator_run_id="eval-1",
    )
    card = scored["card"]
    assert isinstance(card, dict)
    assert container.ctx.snapshots.commit("snap-new", [], schema_version=1) == 2

    result = run_job(
        container,
        "rescore",
        {
            "card_id": card["card_id"],
            "current_snapshot_id": "snap-new",
            "current_corpus_version": 2,
            "snapshot_state": "calibration",
            "evaluator_run_id": "payload-must-not-control-provenance",
        },
        AS_OF,
    )

    assert result["status"] == "succeeded"
    assert result["card"]["snapshot_id"] == "snap-new"
    assert str(result["card"]["evaluator_run_id"]).startswith("rescore:")
    job_row = container.database.fetchone("SELECT status FROM nsqd_jobs WHERE type = 'rescore'")
    assert job_row is not None
    assert job_row["status"] == "succeeded"


def test_rescore_rejects_corpus_version_mismatch() -> None:
    ctx = _ctx()
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)

    with pytest.raises(ValueError, match="current_corpus_version does not match snapshot"):
        _rescore(ctx).run(
            card_id=str(card["card_id"]),
            current_snapshot_id="snap-old",
            current_corpus_version=999,
            snapshot_state="smoke_only",
            evaluator_run_id="eval-2",
        )


def test_rescore_unknown_card_raises() -> None:
    ctx = _ctx()
    with pytest.raises(ValueError, match="unknown card_id"):
        _rescore(ctx).run(
            card_id="missing",
            current_snapshot_id="snap",
            current_corpus_version=1,
            snapshot_state="smoke_only",
            evaluator_run_id="eval-2",
        )


def test_rescore_applies_injected_tau_instead_of_ignoring_composition() -> None:
    embedder = HashParaphraseEmbedder()
    ctx = _ctx()
    harvest = HarvestUseCase(
        harvest=NullHarvestStore(ctx.records, ctx.snapshots),
        clock=ctx.clock,
        index=ctx.index,
        embedder=embedder,
    ).run(
        {
            "records": [
                {
                    "type": "paper",
                    "paraphrase": f"Approved finance paraphrase {index}",
                    "source": f"doi:10.1/rescore-tau-{index}",
                    "domain_policy_id": "finance/1",
                }
                for index in range(1, 6)
            ]
        }
    )
    old_snapshot = str(harvest["snapshot_id"])
    record_ids = [str(item) for item in harvest["record_ids"]]
    candidate = _candidate()
    candidate["paraphrase"] = "Approved finance paraphrase 1"
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate, axiom="x", generator_run_id="gen-tau"
    )
    GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        embedder=embedder,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=old_snapshot,
        corpus_version=int(harvest["corpus_version"]),
        snapshot_state="calibration",
    )
    ScoreUseCase(
        candidates=ctx.candidates,
        cards=ctx.cards,
        snapshots=ctx.snapshots,
        records=ctx.records,
        tau=None,
    ).run(
        candidate_artifact_hash=artifact_hash,
        evaluator_run_id="eval-old",
        snapshot_id=old_snapshot,
        corpus_version=int(harvest["corpus_version"]),
        snapshot_state="calibration",
    )
    new_version = ctx.snapshots.commit("snap-new", record_ids, schema_version=1)
    for record_id in record_ids:
        record = ctx.records.get(record_id)
        assert record is not None
        ctx.index.upsert("snap-new", record_id, embedder.embed(str(record["paraphrase"])))

    result = RescoreUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        cards=ctx.cards,
        embedder=embedder,
        tau=0.45,
    ).run(
        card_id=artifact_hash,
        current_snapshot_id="snap-new",
        current_corpus_version=new_version,
        snapshot_state="calibration",
        evaluator_run_id="eval-new",
    )
    stored = ctx.candidates.get_artifact(artifact_hash)
    assert stored is not None
    evidence = stored["grounding"]["evidence"]
    assert isinstance(evidence, float)
    assert evidence < 0.45
    assert stored["novelty"]["tau"] == 0.45
    assert stored["novelty"]["term"] == 0
    assert result["needs_re_score"] is True


def test_handle_rescore_uses_context_tau() -> None:
    ctx = _ctx()
    ctx.novelty_threshold_tau = 0.30
    scored = _score_on(ctx, snapshot_id="snap-old", corpus_version=1, evaluator_run_id="eval-1")
    card = scored["card"]
    assert isinstance(card, dict)
    ctx.snapshots.commit("snap-new", [], schema_version=1)
    handle_rescore(
        ctx,
        NsqdJob(
            job_id="jr-tau",
            type="rescore",
            status="running",
            payload={
                "card_id": card["card_id"],
                "current_snapshot_id": "snap-new",
                "current_corpus_version": 2,
                "snapshot_state": "smoke_only",
            },
            attempts=1,
            max_attempts=3,
            run_after=None,
        ),
    )
    stored = ctx.candidates.get_artifact(str(card["candidate_artifact_hash"]))
    assert stored is not None
    assert stored["novelty"]["tau"] == 0.30
