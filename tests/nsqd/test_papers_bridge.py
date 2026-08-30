from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nsqd.app.use_cases import AcquireCorpusUseCase, ProjectPaperUseCase, PromoteSnapshotUseCase
from nsqd.composition import build_container
from nsqd.domain.acquisition import CANDIDATES_PER_BATCH
from nsqd.domain.policy import FINANCE_POLICY
from nsqd.infra.papers_bridge import (
    MAX_DRAFT_PARAPHRASE_CHARS,
    MAX_DRAFT_SOURCE_CHARS,
    AnalysisDefaults,
    PapersAcquisitionBridge,
)
from nsqd.null_adapters import (
    FixedClock,
    NullAcquisitionCycleStore,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullHarvestStore,
    NullPaperAcquisitionBridge,
    NullPolicyVerdictStore,
)


@dataclass
class _Scholar:
    results: list[dict[str, Any]]
    calls: list[tuple[str, dict[str, Any], int]] = field(default_factory=list)

    def search(
        self,
        query: str,
        filters: dict[str, Any],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.calls.append((query, filters, max_results))
        return list(self.results)


@dataclass
class _Candidates:
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_candidate(self, fields: dict[str, Any]) -> str:
        candidate_id = str(fields["candidate_id"])
        self.rows[candidate_id] = dict(fields)
        return candidate_id

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.rows.get(candidate_id)
        return dict(row) if row is not None else None

    def get_candidate_by_source(self, source: str, source_paper_id: str) -> dict[str, Any] | None:
        for row in self.rows.values():
            if row.get("source") == source and row.get("source_paper_id") == source_paper_id:
                return dict(row)
        return None

    def mark_imported(self, candidate_id: str, paper_id: str) -> None:
        self.rows[candidate_id]["imported_paper_id"] = paper_id


@dataclass
class _Importer:
    imported: list[str] = field(default_factory=list)

    def import_candidate(self, candidate_id: str) -> str:
        self.imported.append(candidate_id)
        return f"paper-{candidate_id[:8]}"


@dataclass
class _Analyzer:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return "run-1"


@dataclass
class _Papers:
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, paper_id: str) -> dict[str, Any] | None:
        row = self.rows.get(paper_id)
        return dict(row) if row is not None else None


@dataclass
class _ImportUC:
    inner: _Importer = field(default_factory=_Importer)

    def import_candidate(self, candidate_id: str, **_kwargs: Any) -> str:
        return self.inner.import_candidate(candidate_id)


def _bridge(**overrides: Any) -> PapersAcquisitionBridge:
    scholar = overrides.pop("scholar", _Scholar([{"source_paper_id": "s2-1", "title": "A"}]))
    candidates = overrides.pop("candidates", _Candidates())
    importer = overrides.pop("importer", _Importer())
    analyzer = overrides.pop("analyzer", _Analyzer())
    papers = overrides.pop("papers", _Papers())
    discover = overrides.pop("discover_candidates", None)
    from papers.app.use_cases.discovery import DiscoverCandidatesUseCase

    return PapersAcquisitionBridge(
        discover_candidates=discover
        or DiscoverCandidatesUseCase(scholar_client=scholar, candidate_store=candidates),
        import_candidate=overrides.pop("import_candidate", _ImportUC(importer)),
        run_analysis=analyzer,
        paper_store=papers,
        analysis_defaults=overrides.pop(
            "analysis_defaults",
            AnalysisDefaults(
                prompt_id="prompt-1",
                profile_id="profile-1",
                model_name="model-1",
            ),
        ),
        get_markdown=overrides.pop("get_markdown", lambda _paper_id: "markdown"),
        llm_client=overrides.pop("llm_client", _LLM()),
        **overrides,
    )


def test_discover_returns_pending_candidates_and_bounds_batch() -> None:
    scholar = _Scholar(
        [{"source_paper_id": f"s2-{i}", "title": f"T{i}"} for i in range(3)],
    )
    bridge = _bridge(scholar=scholar)
    found = bridge.discover("finance recall", {"type": "paper"})
    assert scholar.calls[0][2] == CANDIDATES_PER_BATCH
    assert [item["source_paper_id"] for item in found] == ["s2-0", "s2-1", "s2-2"]
    assert all(item.get("review_status") != "approved" for item in found)
    assert all("candidate_id" in item for item in found)


def test_shortlist_is_pending_and_cannot_invent_or_approve() -> None:
    bridge = _bridge()
    candidates = [
        {"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"},
        {"candidate_id": "c2", "source_paper_id": "s2-2", "title": "B"},
    ]
    shortlisted = bridge.shortlist(
        candidates,
        limit=1,
        insufficiency_query="finance/1 expected_cell_empty paper",
        filters={"type": "paper"},
        failure_context={"failures": ["expected_cell_empty"]},
    )
    assert len(shortlisted) == 1
    assert shortlisted[0]["source_paper_id"] == "s2-1"
    assert shortlisted[0]["review_status"] == "pending"


def test_shortlist_follows_llm_order_and_drops_unknown_ids() -> None:
    llm = _LLM(shortlist_text='["c2", "missing", "c1"]')
    bridge = _bridge(llm_client=llm)
    candidates = [
        {"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"},
        {"candidate_id": "c2", "source_paper_id": "s2-2", "title": "B"},
    ]
    shortlisted = bridge.shortlist(
        candidates,
        limit=2,
        insufficiency_query=(
            "finance/1 expected_cell_empty "
            "mechanism=flow-driven|target=drawdown|horizon=intraday paper"
        ),
        filters={"type": "paper"},
        failure_context={
            "failures": ["expected_cell_empty"],
            "search_context": {
                "missing_cell_ids": ["mechanism=flow-driven|target=drawdown|horizon=intraday"]
            },
        },
    )
    assert [item["candidate_id"] for item in shortlisted] == ["c2", "c1"]
    assert [item["llm_rank"] for item in shortlisted] == [1, 2]
    assert all(item["review_status"] == "pending" for item in shortlisted)
    assert "Do not mark any candidate approved" in llm.prompts[0]
    assert "finance/1 expected_cell_empty" in llm.prompts[0]
    assert '"type": "paper"' in llm.prompts[0]
    assert '"failures": ["expected_cell_empty"]' in llm.prompts[0]


def test_shortlist_uses_configured_model_name() -> None:
    llm = _LLM()
    bridge = _bridge(
        llm_client=llm,
        analysis_defaults=AnalysisDefaults(
            prompt_id="prompt-1",
            profile_id="profile-1",
            model_name="acquire-model-42",
        ),
    )
    bridge.shortlist(
        [{"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"}],
        limit=1,
        insufficiency_query="finance/1 expected_cell_empty paper",
        filters={"type": "paper"},
        failure_context={"failures": ["expected_cell_empty"]},
    )
    assert llm.models == ["acquire-model-42"]


def test_shortlist_returns_empty_for_non_positive_limit_without_llm_call() -> None:
    llm = _LLM()
    bridge = _bridge(llm_client=llm)
    candidates = [{"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"}]
    assert (
        bridge.shortlist(
            candidates,
            limit=0,
            insufficiency_query="finance/1 expected_cell_empty paper",
            filters={"type": "paper"},
            failure_context={"failures": ["expected_cell_empty"]},
        )
        == []
    )
    assert llm.prompts == []


def test_shortlist_requires_llm_client() -> None:
    bridge = _bridge(llm_client=None)
    with pytest.raises(ValueError, match="llm client"):
        bridge.shortlist(
            [{"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"}],
            limit=1,
            insufficiency_query="finance/1 expected_cell_empty paper",
            filters={"type": "paper"},
            failure_context={"failures": ["expected_cell_empty"]},
        )


def test_shortlist_rejects_unusable_ranking() -> None:
    llm = _LLM(shortlist_text="not-json")
    bridge = _bridge(llm_client=llm)
    with pytest.raises(ValueError, match="JSON array"):
        bridge.shortlist(
            [{"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"}],
            limit=1,
            insufficiency_query="finance/1 expected_cell_empty paper",
            filters={"type": "paper"},
            failure_context={"failures": ["expected_cell_empty"]},
        )


def test_shortlist_parses_fenced_json_array() -> None:
    llm = _LLM(shortlist_text='```json\n["c1"]\n```')
    bridge = _bridge(llm_client=llm)
    shortlisted = bridge.shortlist(
        [{"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"}],
        limit=1,
        insufficiency_query="finance/1 expected_cell_empty paper",
        filters={"type": "paper"},
        failure_context={"failures": ["expected_cell_empty"]},
    )
    assert shortlisted[0]["candidate_id"] == "c1"


def test_shortlist_rejects_ranking_with_no_known_ids() -> None:
    llm = _LLM(shortlist_text='["missing"]')
    bridge = _bridge(llm_client=llm)
    with pytest.raises(ValueError, match="no known candidate"):
        bridge.shortlist(
            [{"candidate_id": "c1", "source_paper_id": "s2-1", "title": "A"}],
            limit=1,
            insufficiency_query="finance/1 expected_cell_empty paper",
            filters={"type": "paper"},
            failure_context={"failures": ["expected_cell_empty"]},
        )


def test_stage_import_and_analyze_use_paper_pipeline() -> None:
    importer = _Importer()
    analyzer = _Analyzer()
    bridge = _bridge(importer=importer, analyzer=analyzer)
    paper_id = bridge.stage_import({"candidate_id": "abcd1234", "title": "A"})
    assert paper_id == "paper-abcd1234"
    assert importer.imported == ["abcd1234"]
    bridge.enqueue_analyze(paper_id)
    assert analyzer.calls == [
        {
            "paper_id": paper_id,
            "prompt_id": "prompt-1",
            "prompt_version_id": None,
            "profile_id": "profile-1",
            "model_name": "model-1",
        }
    ]


def test_real_bridge_stages_candidates_through_acquisition_use_case() -> None:
    importer = _Importer()
    analyzer = _Analyzer()
    bridge = _bridge(
        scholar=_Scholar([{"source_paper_id": "s2-1", "title": "A"}]),
        importer=importer,
        analyzer=analyzer,
    )
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    snapshots.commit("snap", [], schema_version=1)
    policy = replace(
        FINANCE_POLICY,
        expected_cells=frozenset({"mechanism=flow-driven|target=drawdown|horizon=intraday"}),
        recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
    )
    clock = FixedClock(datetime(2024, 1, 1, tzinfo=UTC))
    acquire = AcquireCorpusUseCase(
        cycles=NullAcquisitionCycleStore(),
        promote=PromoteSnapshotUseCase(
            snapshots=snapshots,
            records=records,
            verdicts=NullPolicyVerdictStore(),
            clock=clock,
            policies={policy.policy_id: policy},
        ),
        bridge=bridge,
        project=ProjectPaperUseCase(
            harvest=NullHarvestStore(records, snapshots),
            records=records,
            snapshots=snapshots,
            clock=clock,
            approved_projection_digests=frozenset(),
        ),
    )

    result = acquire.run(
        snapshot_id="snap",
        domain_policy_id=policy.policy_id,
        target="calibration",
    )

    assert result["stopped"] == "pending_human_approval"
    assert importer.imported
    assert analyzer.calls


@dataclass
class _LLM:
    text: str = "Condition allocation on dealer convexity regime."
    shortlist_text: str | None = None
    prompts: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> Any:
        self.prompts.append(prompt)
        self.models.append(model)
        if "JSON array of candidate_id strings" in prompt:
            if self.shortlist_text is not None:
                body = self.shortlist_text
            else:
                payload = json.loads(prompt.rsplit("\n\n", 1)[-1])
                rows = payload["candidates"]
                body = json.dumps([str(row["candidate_id"]) for row in rows])
            return type("Resp", (), {"text": body})()
        return type("Resp", (), {"text": self.text})()


def test_draft_projection_is_never_approved() -> None:
    papers = _Papers(rows={"p1": {"paper_id": "p1", "title": "Title", "abstract": "Abs"}})
    llm = _LLM(text="review_status: approved\nparaphrase: keep pending")
    bridge = _bridge(papers=papers, llm_client=llm)
    draft = bridge.draft_projection("p1")
    assert draft["paper_id"] == "p1"
    assert draft["review_status"] == "pending"
    assert draft["paraphrase_source"] == "model"
    assert draft["paraphrase"] == "review_status: approved\nparaphrase: keep pending"
    assert llm.models == ["model-1"]


def test_draft_projection_uses_llm_not_source_text() -> None:
    papers = _Papers(rows={"p1": {"abstract": "COPY ME ABSTRACT"}})
    llm = _LLM(text="Dealer gamma imbalance under illiquidity is a flow mechanism.")
    bridge = _bridge(
        papers=papers,
        llm_client=llm,
        get_markdown=lambda _paper_id: "COPY ME MARKDOWN",
    )
    draft = bridge.draft_projection("p1")
    assert draft["paraphrase"] == "Dealer gamma imbalance under illiquidity is a flow mechanism."
    assert "COPY ME" not in draft["paraphrase"]
    assert "Do not mark the draft as approved" in llm.prompts[0]
    assert "COPY ME MARKDOWN" in llm.prompts[0]


def test_draft_projection_uses_configured_model_name() -> None:
    papers = _Papers(rows={"p1": {"abstract": "Abs"}})
    llm = _LLM(text="Bounded draft")
    bridge = _bridge(
        papers=papers,
        llm_client=llm,
        analysis_defaults=AnalysisDefaults(
            prompt_id="prompt-1",
            profile_id="profile-1",
            model_name="acquire-model-42",
        ),
    )
    draft = bridge.draft_projection("p1")
    assert draft["paraphrase"] == "Bounded draft"
    assert llm.models == ["acquire-model-42"]


def test_draft_projection_bounds_source_sent_to_llm() -> None:
    papers = _Papers(rows={"p1": {"abstract": "Abs"}})
    source = "X" * (MAX_DRAFT_SOURCE_CHARS + 50)
    llm = _LLM(text="Bounded draft")
    bridge = _bridge(papers=papers, llm_client=llm, get_markdown=lambda _paper_id: source)
    bridge.draft_projection("p1")
    prompt_source = llm.prompts[0].rsplit("\n\n", 1)[-1]
    assert len(prompt_source) == MAX_DRAFT_SOURCE_CHARS
    assert prompt_source == source[:MAX_DRAFT_SOURCE_CHARS]


def test_draft_projection_rejects_overlong_llm_text() -> None:
    papers = _Papers(rows={"p1": {"abstract": "Abs"}})
    bridge = _bridge(
        papers=papers,
        llm_client=_LLM(text="x" * (MAX_DRAFT_PARAPHRASE_CHARS + 1)),
    )
    with pytest.raises(ValueError, match="too long"):
        bridge.draft_projection("p1")


def test_draft_projection_requires_llm_client() -> None:
    papers = _Papers(rows={"p1": {"abstract": "Abs"}})
    bridge = _bridge(papers=papers, llm_client=None)
    with pytest.raises(ValueError, match="llm client"):
        bridge.draft_projection("p1")


def test_draft_projection_rejects_empty_llm_text() -> None:
    papers = _Papers(rows={"p1": {"abstract": "Abs"}})
    bridge = _bridge(papers=papers, llm_client=_LLM(text="  "))
    with pytest.raises(ValueError, match="empty"):
        bridge.draft_projection("p1")


def test_draft_projection_requires_paper_text() -> None:
    papers = _Papers(rows={"p1": {}})
    bridge = _bridge(papers=papers, get_markdown=lambda _paper_id: None)
    with pytest.raises(ValueError, match="paper text"):
        bridge.draft_projection("p1")


def test_null_paper_bridge_is_fail_closed() -> None:
    bridge = NullPaperAcquisitionBridge()
    assert bridge.discover("q", {}) == []
    assert bridge.shortlist([{"paper_id": "p1"}], limit=1) == [{"paper_id": "p1"}]
    assert bridge.shortlist([{"paper_id": "p1"}], limit=0) == []
    with pytest.raises(RuntimeError, match="not configured"):
        bridge.stage_import({"paper_id": "p1"})
    with pytest.raises(RuntimeError, match="not configured"):
        bridge.enqueue_analyze("p1")
    with pytest.raises(RuntimeError, match="not configured"):
        bridge.draft_projection("p1")


def test_discover_without_candidate_lookup_returns_ids_only() -> None:
    class _BareDiscover:
        def discover(
            self,
            query: str,
            filters: dict[str, Any],
            max_results: int,
            page_size: int | None = None,
            offset: int = 0,
        ) -> list[str]:
            return ["c1"]

    bridge = _bridge(discover_candidates=_BareDiscover())
    with pytest.raises(ValueError, match="candidate lookup is required"):
        bridge.discover("q", {})
    with_lookup = _bridge(
        discover_candidates=_BareDiscover(),
        candidate_lookup=_Candidates(rows={"c1": {"source_paper_id": "s2-1", "title": "A"}}),
    )
    assert with_lookup.discover("q", {})[0]["source_paper_id"] == "s2-1"
    missing_source = _bridge(
        discover_candidates=_BareDiscover(),
        candidate_lookup=_Candidates(rows={"c1": {"title": "A"}}),
    )
    with pytest.raises(ValueError, match="source_paper_id is required"):
        missing_source.discover("q", {})


def test_stage_import_requires_candidate_id() -> None:
    bridge = _bridge()
    with pytest.raises(ValueError, match="candidate_id is required"):
        bridge.stage_import({"title": "A"})


def test_analysis_defaults_are_required() -> None:
    bridge = _bridge(analysis_defaults=None)
    with pytest.raises(ValueError, match="analysis defaults"):
        bridge.enqueue_analyze("p1")


def test_build_container_composes_injected_paper_bridge(tmp_path: Path) -> None:
    bridge = _bridge()
    container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "index",
        paper_bridge=bridge,
    )
    assert container.ctx.bridge is bridge


def test_approved_digests_persist_across_container_rebuild(tmp_path: Path) -> None:
    digest = "ab" * 32
    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    first = build_container(
        db_path=db,
        index_path=index,
        approved_projection_digests=frozenset({digest}),
    )
    assert digest in first.ctx.approved_projection_digests
    second = build_container(db_path=db, index_path=index)
    assert digest in second.ctx.approved_projection_digests
