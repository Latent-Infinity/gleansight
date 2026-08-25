from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from nsqd.app.use_cases import AcquireCorpusUseCase, ProjectPaperUseCase, PromoteSnapshotUseCase
from nsqd.domain.acquisition import (
    CANDIDATES_PER_BATCH,
    QUERY_BATCH_LIMIT,
    RECHECK_CYCLE_LIMIT,
    STAGED_IMPORT_LIMIT,
)
from nsqd.domain.policy import FINANCE_POLICY, DomainPolicy
from nsqd.domain.project import canonical_reviewed_projection_digest, normalize_paraphrase
from nsqd.domain.snapshot import sha256_hex
from nsqd.null_adapters import (
    FixedClock,
    NullAcquisitionCycleStore,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullHarvestStore,
    NullPolicyVerdictStore,
)
from tests.facts.test_nsqd_acquisition_fallback import FakePaperBridge

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIN_CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"
BATCH_VALUES = (1, 2, 3)
STAGED_VALUES = (1, 2, 3)
CANDIDATE_VALUES = (1, 5, 25)
USEFUL_IDENTITY = "source_paper_id:useful"
DENSE_SMALLEST = (1, 2, 5)
PAGED_SMALLEST = (2, 2, 1)


class PagedPaperBridge(FakePaperBridge):
    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        super().__init__([])
        self.pages = pages

    def discover(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        self.discover_calls += 1
        self.queries.append(query)
        index = self.discover_calls - 1
        if index >= len(self.pages):
            return []
        return list(self.pages[index])


def _search_policy() -> DomainPolicy:
    return replace(
        FINANCE_POLICY,
        expected_cells=frozenset({FIN_CELL}),
        recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
    )


def _approved_projection(paper_id: str) -> tuple[dict[str, Any], str]:
    paraphrase = normalize_paraphrase(f"Human-approved mechanism for {paper_id}.")
    payload = {
        "domain_policy_id": "finance/1",
        "paraphrase": paraphrase,
        "paraphrase_source": "human",
        "source_paper_id": paper_id,
        "source_abstract_sha256": "a" * 64,
        "source_markdown_sha256": "b" * 64,
        "paraphrase_sha256": sha256_hex(paraphrase.encode("utf-8")),
        "human_reviewer": "product",
        "human_approved_at": "2026-08-22T00:00:00+00:00",
        "review_status": "approved",
    }
    return payload, canonical_reviewed_projection_digest(payload)


def _acquire(
    *,
    pages: list[list[dict[str, Any]]],
    approved_projection_digests: frozenset[str] = frozenset(),
) -> tuple[AcquireCorpusUseCase, PagedPaperBridge]:
    policy = _search_policy()
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    snapshots.commit("snap", [], schema_version=1)
    bridge = PagedPaperBridge(pages)
    acquire = AcquireCorpusUseCase(
        cycles=NullAcquisitionCycleStore(),
        promote=PromoteSnapshotUseCase(
            snapshots=snapshots,
            records=records,
            verdicts=NullPolicyVerdictStore(),
            clock=FixedClock(AS_OF),
            policies={policy.policy_id: policy},
        ),
        bridge=bridge,
        project=ProjectPaperUseCase(
            harvest=NullHarvestStore(records, snapshots),
            records=records,
            clock=FixedClock(AS_OF),
            approved_projection_digests=approved_projection_digests,
        ),
    )
    return acquire, bridge


def _patch_budgets(
    monkeypatch: pytest.MonkeyPatch,
    *,
    batches: int,
    staged: int,
    candidates: int,
    rechecks: int = RECHECK_CYCLE_LIMIT,
) -> None:
    import nsqd.app.use_cases as use_cases

    monkeypatch.setattr(use_cases, "QUERY_BATCH_LIMIT", batches)
    monkeypatch.setattr(use_cases, "STAGED_IMPORT_LIMIT", staged)
    monkeypatch.setattr(use_cases, "CANDIDATES_PER_BATCH", candidates)
    monkeypatch.setattr(use_cases, "RECHECK_CYCLE_LIMIT", rechecks)


def _dense_first_page() -> list[list[dict[str, Any]]]:
    row = [{"source_paper_id": "dud", "title": "Dud"}]
    row.append({"source_paper_id": "useful", "title": "Useful"})
    row.extend({"source_paper_id": f"extra-{index}", "title": f"E{index}"} for index in range(23))
    return [row]


def _useful_on_second_page() -> list[list[dict[str, Any]]]:
    first = [{"source_paper_id": f"dud-{index}", "title": f"D{index}"} for index in range(25)]
    return [first, [{"source_paper_id": "useful", "title": "Useful"}]]


def _stages_useful(
    monkeypatch: pytest.MonkeyPatch,
    budget: tuple[int, int, int],
    pages: list[list[dict[str, Any]]],
) -> bool:
    _patch_budgets(
        monkeypatch,
        batches=budget[0],
        staged=budget[1],
        candidates=budget[2],
    )
    acquire, _bridge = _acquire(pages=pages)
    result = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    identities = [str(item) for item in result.get("staged_identities") or []]
    return USEFUL_IDENTITY in identities


def _winning_budgets(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[list[dict[str, Any]]],
) -> list[tuple[int, int, int]]:
    winners: list[tuple[int, int, int]] = []
    for batches in BATCH_VALUES:
        for staged in STAGED_VALUES:
            for candidates in CANDIDATE_VALUES:
                budget = (batches, staged, candidates)
                if _stages_useful(monkeypatch, budget, pages):
                    winners.append(budget)
    return winners


def test_production_acquisition_ceilings_remain_the_current_defaults() -> None:
    assert QUERY_BATCH_LIMIT == 3
    assert CANDIDATES_PER_BATCH == 25
    assert STAGED_IMPORT_LIMIT == 3
    assert RECHECK_CYCLE_LIMIT == 2


def test_dense_first_page_needs_two_imports_and_five_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _dense_first_page()
    winners = _winning_budgets(monkeypatch, pages)
    assert winners[0] == DENSE_SMALLEST
    assert (QUERY_BATCH_LIMIT, STAGED_IMPORT_LIMIT, CANDIDATES_PER_BATCH) in winners
    assert _stages_useful(monkeypatch, (1, 1, 25), pages) is False
    assert _stages_useful(monkeypatch, (1, 3, 1), pages) is False


def test_second_page_hit_requires_spare_import_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = _useful_on_second_page()
    winners = _winning_budgets(monkeypatch, pages)
    assert winners[0] == PAGED_SMALLEST
    assert (QUERY_BATCH_LIMIT, STAGED_IMPORT_LIMIT, CANDIDATES_PER_BATCH) not in winners
    assert _stages_useful(monkeypatch, (3, 3, 25), pages) is False
    assert _stages_useful(monkeypatch, (2, 1, 1), pages) is False


def test_recheck_limit_one_stops_without_a_second_search(monkeypatch: pytest.MonkeyPatch) -> None:
    projection, digest = _approved_projection("useful")
    _patch_budgets(monkeypatch, batches=1, staged=1, candidates=1, rechecks=1)
    acquire, bridge = _acquire(
        pages=[[{"source_paper_id": "useful", "title": "Useful"}]],
        approved_projection_digests=frozenset({digest}),
    )
    staged = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert staged["stopped"] == "pending_human_approval"
    approved = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
        human_decision="approve",
        approved_projections=[projection],
    )
    assert approved["projected"] is True
    assert approved["stopped"] == "recheck_budget"
    assert approved["rechecks"] == 1
    assert bridge.discover_calls == 1


def test_recheck_limit_two_searches_again_after_insufficient_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, digest = _approved_projection("useful")
    _patch_budgets(monkeypatch, batches=1, staged=1, candidates=1, rechecks=2)
    acquire, bridge = _acquire(
        pages=[[{"source_paper_id": "useful", "title": "Useful"}]],
        approved_projection_digests=frozenset({digest}),
    )
    acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    approved = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
        human_decision="approve",
        approved_projections=[projection],
    )
    assert approved["projected"] is True
    assert approved["rechecks"] == 1
    assert approved["stopped"] != "recheck_budget"
    assert bridge.discover_calls >= 2
