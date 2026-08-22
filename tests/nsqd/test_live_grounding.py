from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.app.handlers import NsqdHandlerContext, handle_ground
from nsqd.app.use_cases import DivergeUseCase, GroundUseCase, empty_smoke_snapshot_id
from nsqd.composition import build_container
from nsqd.domain.grounding import LIVE_SEARCH_BUDGET, apply_live_hits, live_escalation_allowed
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
from nsqd.runner import run_job

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"


class RecordingSearch:
    def __init__(self, hits: list[list[dict[str, Any]]] | None = None) -> None:
        self.queries: list[str] = []
        self._hits = list(hits or [])

    def search(self, query: str, *args: object, **kwargs: object) -> list[dict[str, Any]]:
        self.queries.append(query)
        if not self._hits:
            return []
        return list(self._hits.pop(0))


class StrictHybridSearch:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.calls: list[tuple[str, int]] = []
        self._hits = hits

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((query, limit))
        return list(self._hits)


class StrictScholarSearch:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.calls: list[tuple[str, dict[str, Any], int, int, int]] = []
        self._hits = hits

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.calls.append((query, filters, max_results, page_size, offset))
        return list(self._hits)


class _ForbiddenSearch:
    def query(self, *args: object, **kwargs: object) -> list[object]:
        raise AssertionError("paper hybrid search must not be called")

    def search(self, *args: object, **kwargs: object) -> list[object]:
        raise AssertionError("live search must not be called")


def _load_card(name: str) -> dict[str, Any]:
    payload = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


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
        scholar_client=scholar if scholar is not None else _ForbiddenSearch(),
        paper_vector_index=hybrid if hybrid is not None else _ForbiddenSearch(),
    )


def _diverge(ctx: NsqdHandlerContext) -> str:
    candidate = _load_card("gamma-flow.yaml")
    return DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate=candidate,
        axiom="predictors assume stationary return signal",
        generator_run_id="gen-1",
    )


def test_live_escalation_only_after_local_miss_on_non_smoke() -> None:
    assert live_escalation_allowed(snapshot_state="smoke_only", local_class="unevaluated") is False
    assert (
        live_escalation_allowed(snapshot_state="calibration", local_class="already_done") is False
    )
    assert live_escalation_allowed(snapshot_state="calibration", local_class="unevaluated") is True
    assert (
        live_escalation_allowed(snapshot_state="production_valid", local_class="unevaluated")
        is True
    )


def test_live_hits_do_not_claim_already_done() -> None:
    klass, confidence = apply_live_hits(
        local_class="unevaluated",
        local_confidence=0.0,
        live_hits=[{"title": "prior art"}],
    )
    assert klass == "related_partial"
    assert confidence == 0.4
    klass, confidence = apply_live_hits(
        local_class="already_done",
        local_confidence=1.0,
        live_hits=[{"title": "prior art"}],
    )
    assert klass == "already_done"
    assert confidence == 1.0


def test_smoke_grounding_does_not_call_live_or_hybrid_when_wired() -> None:
    live = RecordingSearch()
    hybrid = RecordingSearch()
    ctx = _ctx(scholar=live, hybrid=hybrid)
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    artifact_hash = _diverge(ctx)
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=live,
        hybrid_search=hybrid,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="smoke_only",
    )
    assert grounding["grounding_class"] == "unevaluated"
    assert grounding["live_call_count"] == 0
    assert live.queries == []
    assert hybrid.queries == []
    assert ctx.records.list_ids() == []


def test_calibration_empty_snapshot_escalates_within_budget() -> None:
    live = RecordingSearch(hits=[[], [], [{"title": "fourth would hit"}]])
    hybrid = RecordingSearch()
    ctx = _ctx(scholar=live, hybrid=hybrid)
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    artifact_hash = _diverge(ctx)
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=live,
        hybrid_search=hybrid,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="calibration",
    )
    assert grounding["grounding_class"] == "unevaluated"
    assert grounding["live_call_count"] <= LIVE_SEARCH_BUDGET
    assert grounding["live_call_count"] == len(live.queries) + len(hybrid.queries)
    assert len(live.queries) + len(hybrid.queries) == LIVE_SEARCH_BUDGET
    assert ctx.records.list_ids() == []


def test_hybrid_hit_skips_scholar_and_stays_out_of_corpus() -> None:
    live = RecordingSearch(hits=[[{"title": "should not be used"}]])
    hybrid = RecordingSearch(hits=[[{"paper_id": "p1", "title": "local paper", "score": 0.75}]])
    ctx = _ctx(scholar=live, hybrid=hybrid)
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    artifact_hash = _diverge(ctx)
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=live,
        hybrid_search=hybrid,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="calibration",
    )
    assert grounding["grounding_class"] == "related_partial"
    assert grounding["live_call_count"] == 1
    assert grounding["closest_prior_art"] == {
        "source": "hybrid",
        "paper_id": "p1",
        "score": 0.75,
    }
    assert "query" not in grounding["live_calls"][0]
    assert len(grounding["live_calls"][0]["query_sha256"]) == 64
    assert hybrid.queries
    assert live.queries == []
    assert ctx.records.list_ids() == []


def test_local_corpus_hit_does_not_escalate() -> None:
    live = RecordingSearch(hits=[[{"title": "live"}]])
    hybrid = RecordingSearch(hits=[[{"title": "hybrid"}]])
    ctx = _ctx(scholar=live, hybrid=hybrid)
    ctx.records.put(
        {
            "record_id": "fin",
            "type": "paper",
            "domain_policy_id": "finance/1",
            "source": "doi:10.0000/example",
            "paraphrase": "corpus",
        }
    )
    ctx.snapshots.commit("snap", ["fin"], schema_version=1)
    artifact_hash = DivergeUseCase(candidates=ctx.candidates, cards=ctx.cards, clock=ctx.clock).run(
        candidate={
            **_load_card("gamma-flow.yaml"),
            "source": "https://doi.org/10.0000/example",
        },
        axiom="predictors assume stationary return signal",
        generator_run_id="gen-1",
    )
    grounding = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=live,
        hybrid_search=hybrid,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id="snap",
        corpus_version=1,
        snapshot_state="calibration",
    )
    assert grounding["grounding_class"] == "already_done"
    assert grounding["closest_prior_art"] == {
        "source": "corpus",
        "record_id": "fin",
        "record_type": "paper",
    }
    assert grounding["live_call_count"] == 0
    assert live.queries == []
    assert hybrid.queries == []


def test_handle_ground_uses_injected_live_clients_on_calibration() -> None:
    live = RecordingSearch()
    hybrid = RecordingSearch(hits=[[{"paper_id": "p1", "score": 0.75}]])
    ctx = _ctx(scholar=live, hybrid=hybrid)
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)
    artifact_hash = _diverge(ctx)
    result = handle_ground(
        ctx,
        NsqdJob(
            job_id="g1",
            type="ground",
            status="running",
            payload={
                "candidate_artifact_hash": artifact_hash,
                "snapshot_id": sid,
                "corpus_version": 1,
                "snapshot_state": "calibration",
            },
            attempts=1,
            max_attempts=3,
            run_after=None,
        ),
    )
    assert result["grounding_class"] == "related_partial"
    assert result["live_call_count"] == 1
    assert hybrid.queries
    assert live.queries == []


def test_grounding_calls_real_hybrid_and_scholar_api_shapes() -> None:
    hybrid = StrictHybridSearch([])
    scholar = StrictScholarSearch([{"source_paper_id": "p1", "title": "Prior art"}])
    ctx = _ctx(scholar=scholar, hybrid=hybrid)
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)

    result = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=scholar,
        hybrid_search=hybrid,
    ).run(
        candidate_artifact_hash=_diverge(ctx),
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="calibration",
    )

    assert result["grounding_class"] == "related_partial"
    assert len(hybrid.calls) == 1
    assert hybrid.calls[0][1] == LIVE_SEARCH_BUDGET
    assert scholar.calls == [(hybrid.calls[0][0], {}, 1, 1, 0)]


def test_container_dispatches_ground_with_injected_live_clients(tmp_path: Path) -> None:
    hybrid = StrictHybridSearch([{"paper_id": "p1", "score": 0.75}])
    scholar = StrictScholarSearch([])
    container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "index",
        clock=FixedClock(AS_OF),
        scholar_client=scholar,
        paper_hybrid_search=hybrid,
    )
    sid = empty_smoke_snapshot_id()
    container.ctx.snapshots.commit(sid, [], schema_version=1)
    artifact_hash = DivergeUseCase(
        candidates=container.ctx.candidates,
        cards=container.ctx.cards,
        clock=container.ctx.clock,
    ).run(
        candidate=_load_card("gamma-flow.yaml"),
        axiom="predictors assume stationary return signal",
        generator_run_id="gen-1",
    )

    result = run_job(
        container,
        "ground",
        {
            "candidate_artifact_hash": artifact_hash,
            "snapshot_id": sid,
            "corpus_version": 1,
            "snapshot_state": "calibration",
        },
        AS_OF,
    )

    assert result["grounding_class"] == "related_partial"
    assert len(hybrid.calls) == 1
    assert hybrid.calls[0][1] == LIVE_SEARCH_BUDGET
    assert scholar.calls == []


def test_malformed_external_hits_do_not_reduce_novelty_or_persist_query() -> None:
    hybrid = StrictHybridSearch(
        [
            {"title": "missing identity and score"},
            {"paper_id": "p1", "score": float("nan")},
            {"paper_id": "p2", "score": -1.0},
        ]
    )
    scholar = StrictScholarSearch([{"title": "missing source identity"}])
    ctx = _ctx(scholar=scholar, hybrid=hybrid)
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)

    result = GroundUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        index=ctx.index,
        candidates=ctx.candidates,
        live_search=scholar,
        hybrid_search=hybrid,
    ).run(
        candidate_artifact_hash=_diverge(ctx),
        snapshot_id=sid,
        corpus_version=1,
        snapshot_state="calibration",
    )

    assert result["grounding_class"] == "unevaluated"
    assert result["closest_prior_art"] is None
    assert result["live_call_count"] == LIVE_SEARCH_BUDGET
    assert all("query" not in call for call in result["live_calls"])
    assert all(len(call["query_sha256"]) == 64 for call in result["live_calls"])


def test_grounding_rejects_snapshot_corpus_version_mismatch() -> None:
    ctx = _ctx()
    sid = empty_smoke_snapshot_id()
    ctx.snapshots.commit(sid, [], schema_version=1)

    try:
        GroundUseCase(
            snapshots=ctx.snapshots,
            records=ctx.records,
            index=ctx.index,
            candidates=ctx.candidates,
        ).run(
            candidate_artifact_hash=_diverge(ctx),
            snapshot_id=sid,
            corpus_version=2,
        )
    except ValueError as exc:
        assert str(exc) == "corpus_version does not match snapshot"
    else:
        raise AssertionError("expected corpus version mismatch rejection")
