from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from nsqd.app.handlers import (
    NsqdHandlerContext,
    handle_acquire,
    handle_diverge,
    handle_ground,
    handle_map,
    handle_project,
    handle_rescore,
    handle_score,
)
from nsqd.app.use_cases import (
    ArchiveInsertUseCase,
    DivergeUseCase,
    GroundUseCase,
    ScoreUseCase,
    candidate_body,
    empty_smoke_snapshot_id,
)
from nsqd.domain.policy import FINANCE_POLICY
from nsqd.domain.snapshot import snapshot_id
from nsqd.domain.status import CellStatus
from nsqd.null_adapters import (
    FixedClock,
    NullAcquisitionCycleStore,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullFrontierCardStore,
    NullHarvestStore,
    NullMorphospaceStore,
    NullNsqdCandidateStore,
    NullPaperAcquisitionBridge,
    NullPolicyVerdictStore,
)
from nsqd.ports import NsqdJob

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
AS_OF = datetime(2024, 1, 1, tzinfo=UTC)


class _ForbiddenSearch:
    def query(self, *args: object, **kwargs: object) -> list[object]:
        raise AssertionError("paper hybrid search must not be called")

    def search(self, *args: object, **kwargs: object) -> list[object]:
        raise AssertionError("live search must not be called")


def _load_card(name: str) -> dict[str, Any]:
    payload = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


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
        scholar_client=_ForbiddenSearch(),
        paper_vector_index=_ForbiddenSearch(),
    )


def test_diverge_persists_artifact_and_evaluate_reloads_by_hash() -> None:
    ctx = _ctx()
    candidate = _load_card("gamma-flow.yaml")
    diverge = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock)
    artifact_hash = diverge.run(
        candidate=candidate,
        axiom="predictors assume stationary return signal",
        generator_run_id="gen-1",
    )
    stored = ctx.candidates.get_artifact(artifact_hash)
    assert stored is not None
    assert stored["generator_run_id"] == "gen-1"
    with pytest.raises(ValueError, match="load the artifact by hash"):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="eval-1",
            snapshot_id="unused",
            corpus_version=1,
            snapshot_state="smoke_only",
            live_candidate=candidate,
        )
    with pytest.raises(ValueError, match="evaluator_run_id"):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="gen-1",
            snapshot_id="unused",
            corpus_version=1,
            snapshot_state="smoke_only",
        )


def test_allowlisted_operator_b_provenance_reaches_scored_card() -> None:
    ctx = _ctx()
    candidate = _load_card("gamma-flow.yaml")
    descriptor = candidate["research_descriptor"]
    assert isinstance(descriptor, dict)
    target = FINANCE_POLICY.cell_id(descriptor)
    statuses: dict[str, CellStatus] = {cell_id: "Unknown" for cell_id in FINANCE_POLICY.universe()}
    statuses[target] = "Missing"
    artifact_hash = DivergeUseCase(
        candidates=ctx.candidates,
        cards=ctx.cards,
        clock=ctx.clock,
        enabled_operators=frozenset({"A", "B"}),
    ).run(
        candidate=candidate,
        axioms=[{"statement": "occupy archive whitespace", "cell_id": target}],
        operator="B",
        generator_run_id="gen-b",
        target_cell_id=target,
        cell_statuses=statuses,
    )
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id=sid, corpus_version=1)

    scored = ScoreUseCase(
        candidates=ctx.candidates,
        cards=ctx.cards,
        snapshots=ctx.snapshots,
        records=ctx.records,
    ).run(
        candidate_artifact_hash=artifact_hash,
        evaluator_run_id="eval-b",
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="smoke_only",
    )

    assert scored["card"]["generating_operator"] == "B"


def test_local_grounding_empty_snapshot_is_unevaluated_and_ignores_live_search() -> None:
    ctx = _ctx()
    candidate = _load_card("gamma-flow.yaml")
    sid = empty_smoke_snapshot_id()
    assert sid == snapshot_id(records=[], schema_version=1)
    ctx.snapshots.commit(sid, [], schema_version=1)
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="predictors assume stationary return signal",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=ctx.scholar_client,
        hybrid_search=ctx.paper_vector_index,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="smoke_only",
    )
    assert grounding["grounding_class"] == "unevaluated"
    assert grounding["live_call_count"] == 0
    assert grounding["evidence"] is None
    assert [layer["layer"] for layer in grounding["layers"]] == [1, 2, 3, 4]


def test_score_and_archive_reject_smoke_fixtures() -> None:
    ctx = _ctx()
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    for name in ("gamma-flow.yaml", "mechanism-free.yaml"):
        candidate = _load_card(name)
        expected = candidate["expected_outcomes"]
        assert isinstance(expected, dict)
        artifact_hash = DivergeUseCase(
            candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock
        ).run(
            candidate=candidate,
            axiom="predictors assume stationary return signal",
            generator_run_id="gen-1",
        )
        GroundUseCase(
            snapshots=ctx.snapshots,
            records=ctx.records,
            index=ctx.index,
            candidates=ctx.candidates,
        ).run(candidate_artifact_hash=artifact_hash, snapshot_id=sid, corpus_version=1)
        scored = ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="eval-1",
            snapshot_id=sid,
            corpus_version=1,
            snapshot_state="smoke_only",
        )
        assert scored["evidence"] is None
        assert scored["nov"] == expected["nov"]
        assert scored["mech"] == expected["mech"]
        assert scored["fals"] == expected["fals"]
        assert scored["dpred"] == expected["dpred"]
        assert scored["dval"] == expected["dval"]
        assert scored["viability"] == 0
        assert scored["card"]["card_decision"] == "rejected"
        assert not scored["card"]["missing_fields"]
        archived = ArchiveInsertUseCase(cards=ctx.cards).run(scored["card"])
        assert archived["inserted"] is False
        assert archived["reason"] == "viability_zero"
        assert ctx.cards.elite_for_cell(scored["card"]["archive_cell_key"]) is None


def test_handlers_are_callable_without_cli() -> None:
    ctx = _ctx()
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    candidate = _load_card("gamma-flow.yaml")
    diverge_job = NsqdJob(
        job_id="j1",
        type="diverge",
        status="running",
        payload={
            "candidate": candidate,
            "axiom": "predictors assume stationary return signal",
            "generator_run_id": "gen-1",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    diverge_result = handle_diverge(ctx, diverge_job)
    assert diverge_result["status"] == "succeeded"
    artifact_hash = diverge_result["candidate_artifact_hash"]
    ground_job = NsqdJob(
        job_id="j2",
        type="ground",
        status="running",
        payload={
            "candidate_artifact_hash": artifact_hash,
            "snapshot_id": sid,
            "corpus_version": 1,
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    assert handle_ground(ctx, ground_job)["status"] == "succeeded"
    score_job = NsqdJob(
        job_id="j3",
        type="score",
        status="running",
        payload={
            "candidate_artifact_hash": artifact_hash,
            "snapshot_id": sid,
            "corpus_version": 1,
            "evaluator_run_id": "eval-1",
            "snapshot_state": "smoke_only",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    scored = handle_score(ctx, score_job)
    assert scored["status"] == "succeeded"
    assert scored["viability"] == 0
    stored_card = ctx.cards.get_card(artifact_hash)
    assert stored_card is not None
    assert ctx.cards.elite_for_cell(stored_card["archive_cell_key"]) is None


def test_ground_and_score_fail_on_unknown_hash() -> None:
    ctx = _ctx()
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    with pytest.raises(ValueError, match="unknown candidate_artifact_hash"):
        GroundUseCase(
            snapshots=ctx.snapshots,
            records=ctx.records,
            index=ctx.index,
            candidates=ctx.candidates,
        ).run(candidate_artifact_hash="missing", snapshot_id=sid, corpus_version=1)
    with pytest.raises(ValueError, match="unknown candidate_artifact_hash"):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash="missing",
            evaluator_run_id="eval-1",
            snapshot_id=sid,
            corpus_version=1,
            snapshot_state="smoke_only",
        )


def test_score_requires_grounding() -> None:
    ctx = _ctx()
    candidate = _load_card("gamma-flow.yaml")
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    with pytest.raises(ValueError, match="grounded"):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="eval-1",
            snapshot_id="snap",
            corpus_version=1,
            snapshot_state="smoke_only",
        )


def test_ground_hits_exact_source_on_populated_snapshot() -> None:
    ctx = _ctx()
    ctx.records.put(
        {
            "record_id": "r1",
            "source": "doi:10.1/x",
            "type": "paper",
            "tags": [],
            "domain_policy_id": "finance/1",
        }
    )
    ctx.snapshots.commit("snap", ["r1"], schema_version=1)
    candidate = {
        "title": "t",
        "source": "doi:10.1/x",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "flow-driven",
            "target": "drawdown",
            "horizon": "intraday",
        },
    }
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id="snap", corpus_version=1)
    assert grounding["grounding_class"] == "already_done"


def test_ground_matches_normalized_doi_source_forms() -> None:
    ctx = _ctx()
    ctx.records.put(
        {
            "record_id": "r1",
            "source": "https://doi.org/10.1/X/",
            "type": "paper",
            "tags": [],
            "domain_policy_id": "finance/1",
        }
    )
    ctx.snapshots.commit("snap", ["r1"], schema_version=1)
    candidate = {
        "title": "t",
        "source": "doi:10.1/x",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "flow-driven",
            "target": "drawdown",
            "horizon": "intraday",
        },
    }
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id="snap", corpus_version=1)
    assert grounding["grounding_class"] == "already_done"


def test_ground_uses_index_when_query_vector_present() -> None:
    ctx = _ctx()
    ctx.records.put(
        {
            "record_id": "r1",
            "source": "s",
            "type": "code",
            "tags": [],
            "domain_policy_id": "finance/1",
        }
    )
    ctx.index.upsert("snap", "r1", [1.0, 0.0])
    ctx.snapshots.commit("snap", ["r1"], schema_version=1)
    candidate = {
        "title": "t",
        "query_vector": [1.0, 0.0],
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "behavioral",
            "target": "returns",
            "horizon": "intraday",
        },
    }
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id="snap", corpus_version=1)
    assert grounding["evidence"] == pytest.approx(0.0)
    assert grounding["grounding_class"] == "related_partial"
    assert grounding["closest_prior_art"] == {
        "source": "corpus",
        "record_id": "r1",
        "record_type": "code",
        "distance": pytest.approx(0.0),
    }


def test_archive_inserts_nonzero_viability_card() -> None:
    ctx = _ctx()
    card = {
        "card_id": "c-high",
        "domain_policy_id": "finance/1",
        "cell_id": "mechanism=flow-driven|target=drawdown|horizon=intraday",
        "archive_cell_key": "finance/1::mechanism=flow-driven|target=drawdown|horizon=intraday",
        "title": "t",
        "generating_operator": "A",
        "snapshot_id": "snap",
        "corpus_version": 1,
        "viability": 9,
        "nov": 1,
        "mech": 5,
        "fals": 5,
        "dpred": 5,
        "dval": 5,
        "candidate_artifact_hash": "aaa",
        "card_decision": "accepted",
    }
    ctx.cards.put_card(card)
    result = ArchiveInsertUseCase(cards=ctx.cards).run(card)
    assert result["inserted"] is True
    assert ctx.cards.elite_for_cell(card["archive_cell_key"]) == card


def test_score_rejects_incomplete_card() -> None:
    ctx = _ctx()
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    candidate = {
        "title": "",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "flow-driven",
            "target": "drawdown",
            "horizon": "intraday",
        },
    }
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id=sid, corpus_version=1)
    with pytest.raises(ValueError, match="missing required fields"):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="eval-1",
            snapshot_id=sid,
            corpus_version=1,
            snapshot_state="smoke_only",
        )


def test_ground_terminology_and_code_layers_on_populated_snapshot() -> None:
    ctx = _ctx()
    ctx.records.put(
        {
            "record_id": "r1",
            "source": "other",
            "type": "paper",
            "tags": ["terminology"],
            "domain_policy_id": "finance/1",
        }
    )
    ctx.snapshots.commit("snap", ["r1", "ghost"], schema_version=1)
    candidate = {
        "title": "t",
        "source": "nope",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "behavioral",
            "target": "returns",
            "horizon": "intraday",
        },
    }
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id="snap", corpus_version=1)
    assert grounding["grounding_class"] == "renamed"
    assert grounding["closest_prior_art"] == {
        "source": "corpus",
        "record_id": "r1",
        "record_type": "paper",
    }

    ctx.records.put(
        {
            "record_id": "r2",
            "source": "other",
            "type": "code",
            "tags": [],
            "domain_policy_id": "finance/1",
        }
    )
    code_corpus_version = ctx.snapshots.commit("snap-code", ["r2"], schema_version=1)
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate={**candidate, "title": "t2"},
        axiom="x",
        generator_run_id="gen-2",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id="snap-code",
        corpus_version=code_corpus_version,
    )
    assert grounding["grounding_class"] == "already_done"
    assert grounding["confidence"] == 0.9
    assert grounding["closest_prior_art"] == {
        "source": "corpus",
        "record_id": "r2",
        "record_type": "code",
    }


def test_candidate_body_and_diverge_artifact_do_not_alias_nested_payloads() -> None:
    ctx = _ctx()
    candidate: dict[str, Any] = {
        "title": "t",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "flow-driven",
            "target": ["drawdown"],
            "horizon": "intraday",
        },
        "query_vector": [1.0, 0.0],
        "expected_outcomes": {"nov": 0},
    }

    body = candidate_body(candidate)
    candidate["research_descriptor"]["target"].append("returns")
    candidate["query_vector"].append(2.0)

    assert body == {
        "title": "t",
        "domain_policy_id": "finance/1",
        "research_descriptor": {
            "mechanism": "flow-driven",
            "target": ["drawdown"],
            "horizon": "intraday",
        },
        "query_vector": [1.0, 0.0],
    }

    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    stored = ctx.candidates.get_artifact(artifact_hash)
    assert stored is not None
    assert stored["candidate"]["research_descriptor"]["target"] == ["drawdown", "returns"]
    assert stored["candidate"]["query_vector"] == [1.0, 0.0, 2.0]
    stored["candidate"]["research_descriptor"]["target"].append("alias")
    stored["candidate"]["query_vector"].append(3.0)
    again = ctx.candidates.get_artifact(artifact_hash)
    assert again is not None
    assert again["candidate"]["research_descriptor"]["target"] == ["drawdown", "returns"]
    assert again["candidate"]["query_vector"] == [1.0, 0.0, 2.0]


def test_ground_rejects_uncommitted_snapshot_id() -> None:
    ctx = _ctx()
    candidate = _load_card("gamma-flow.yaml")
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )

    with pytest.raises(ValueError, match="unknown snapshot_id"):
        GroundUseCase(
            snapshots=ctx.snapshots,
            records=ctx.records,
            index=ctx.index,
            candidates=ctx.candidates,
        ).run(
            candidate_artifact_hash=artifact_hash,
            snapshot_id="missing-snapshot",
            corpus_version=1,
        )


@pytest.mark.parametrize(
    ("snapshot_id", "corpus_version", "message"),
    [
        ("other-snapshot", 1, "snapshot_id does not match grounded artifact"),
        ("snap", 2, "corpus_version does not match grounded artifact"),
    ],
)
def test_score_rejects_grounding_stamp_mismatch_without_persisting_card(
    snapshot_id: str, corpus_version: int, message: str
) -> None:
    ctx = _ctx()
    ctx.snapshots.commit("snap", [], schema_version=1)
    candidate = _load_card("gamma-flow.yaml")
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id="snap", corpus_version=1)

    with pytest.raises(ValueError, match=message):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="eval-1",
            snapshot_id=snapshot_id,
            corpus_version=corpus_version,
            snapshot_state="smoke_only",
        )

    assert ctx.cards.get_card(artifact_hash) is None


def test_score_rejects_invalid_snapshot_state_without_persisting_card() -> None:
    ctx = _ctx()
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    candidate = _load_card("gamma-flow.yaml")
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="x",
        generator_run_id="gen-1",
    )
    GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
    ).run(candidate_artifact_hash=artifact_hash, snapshot_id=sid, corpus_version=1)

    with pytest.raises(ValueError, match="invalid snapshot_state"):
        ScoreUseCase(
            candidates=ctx.candidates,
            cards=ctx.cards,
            snapshots=ctx.snapshots,
            records=ctx.records,
        ).run(
            candidate_artifact_hash=artifact_hash,
            evaluator_run_id="eval-1",
            snapshot_id=sid,
            corpus_version=1,
            snapshot_state="invalid",
        )

    assert ctx.cards.get_card(artifact_hash) is None


@pytest.mark.parametrize(
    ("handler", "expected_type"),
    [
        (handle_diverge, "diverge"),
        (handle_ground, "ground"),
        (handle_score, "score"),
        (handle_rescore, "rescore"),
        (handle_project, "project"),
        (handle_map, "map"),
        (handle_acquire, "acquire"),
    ],
)
def test_handlers_reject_mismatched_job_type_before_reading_payload(
    handler: Any, expected_type: str
) -> None:
    ctx = _ctx()
    job = NsqdJob(
        job_id="job-1",
        type="not-" + expected_type,
        status="running",
        payload={},
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    with pytest.raises(ValueError, match=f"expected job.type={expected_type}"):
        handler(ctx, job)


def test_acquire_handler_requires_complete_context() -> None:
    ctx = _ctx()
    job = NsqdJob(
        job_id="job-1",
        type="acquire",
        status="running",
        payload={
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "target": "calibration",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    with pytest.raises(ValueError, match="acquisition context is incomplete"):
        handle_acquire(ctx, job)


def test_acquire_handler_rejects_non_mapping_approved_projection() -> None:
    ctx = _ctx()
    ctx.cycles = NullAcquisitionCycleStore()
    ctx.verdicts = NullPolicyVerdictStore()
    ctx.bridge = NullPaperAcquisitionBridge()
    job = NsqdJob(
        job_id="job-1",
        type="acquire",
        status="running",
        payload={
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "target": "calibration",
            "approved_projections": ["not-a-mapping"],
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    with pytest.raises(ValueError, match="list of mappings"):
        handle_acquire(ctx, job)


def test_acquire_handler_passes_approved_digests_to_promotion(monkeypatch) -> None:
    import nsqd.app.handlers as handlers

    captured: dict[str, object] = {}

    class _Promote:
        policies = None

        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def run(self, **_kwargs: object) -> dict[str, object]:
            return {
                "state": "calibration",
                "failures": (),
                "search_context": {},
            }

    ctx = _ctx()
    ctx.approved_projection_digests = frozenset({"a" * 64})
    ctx.cycles = NullAcquisitionCycleStore()
    ctx.verdicts = NullPolicyVerdictStore()
    ctx.bridge = NullPaperAcquisitionBridge()
    ctx.snapshots.commit("snap", [], schema_version=1)
    monkeypatch.setattr(handlers, "PromoteSnapshotUseCase", _Promote)
    job = NsqdJob(
        job_id="job-1",
        type="acquire",
        status="running",
        payload={
            "snapshot_id": "snap",
            "domain_policy_id": "finance/1",
            "target": "calibration",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_acquire(ctx, job)

    assert result["status"] == "succeeded"
    assert captured["approved_harvest_seed_digests"] == ctx.approved_projection_digests
