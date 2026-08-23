from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nsqd.app.use_cases import AcquireCorpusUseCase, ProjectPaperUseCase, PromoteSnapshotUseCase
from nsqd.composition import build_container
from nsqd.domain.acquisition import CANDIDATES_PER_BATCH
from nsqd.domain.policy import FINANCE_POLICY
from nsqd.infra.papers_bridge import AnalysisDefaults, PapersAcquisitionBridge
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
    shortlisted = bridge.shortlist(candidates, limit=1)
    assert len(shortlisted) == 1
    assert shortlisted[0]["source_paper_id"] == "s2-1"
    assert shortlisted[0]["review_status"] == "pending"


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


def test_draft_projection_is_never_approved() -> None:
    papers = _Papers(rows={"p1": {"paper_id": "p1", "title": "Title", "abstract": "Abs"}})
    bridge = _bridge(papers=papers)
    draft = bridge.draft_projection("p1")
    assert draft["paper_id"] == "p1"
    assert draft["review_status"] == "pending"
    assert draft["paraphrase_source"] == "model"
    assert draft["paraphrase"]


def test_null_paper_bridge_is_fail_closed() -> None:
    bridge = NullPaperAcquisitionBridge()
    assert bridge.discover("q", {}) == []
    assert bridge.shortlist([{"paper_id": "p1"}], limit=1) == [{"paper_id": "p1"}]
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
