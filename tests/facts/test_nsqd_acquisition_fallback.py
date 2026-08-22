from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from nsqd.app.use_cases import AcquireCorpusUseCase, PromoteSnapshotUseCase
from nsqd.domain.acquisition import QUERY_BATCH_LIMIT, STAGED_IMPORT_LIMIT
from nsqd.domain.policy import FINANCE_POLICY, DomainPolicy
from nsqd.null_adapters import (
    FixedClock,
    NullAcquisitionCycleStore,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullPolicyVerdictStore,
)

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIN_CELL = "mechanism=flow-driven|target=drawdown|horizon=intraday"


class FakePaperBridge:
    def __init__(
        self,
        candidates: list[dict[str, Any]],
        *,
        shortlist_approved: bool = False,
        draft_approved: bool = False,
        fail_stage: bool = False,
        invent_shortlist: bool = False,
        mutate_shortlist: bool = False,
    ) -> None:
        self.candidates = candidates
        self.shortlist_approved = shortlist_approved
        self.draft_approved = draft_approved
        self.fail_stage = fail_stage
        self.invent_shortlist = invent_shortlist
        self.mutate_shortlist = mutate_shortlist
        self.discover_calls = 0
        self.staged: list[str] = []
        self.analyzed: list[str] = []
        self.drafts: list[dict[str, Any]] = []
        self.queries: list[str] = []
        self.staged_candidates: list[dict[str, Any]] = []

    def discover(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        self.discover_calls += 1
        self.queries.append(query)
        return list(self.candidates)

    def shortlist(self, candidates: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        status = "approved" if self.shortlist_approved else "pending"
        if self.invent_shortlist:
            return [{"paper_id": "invented", "review_status": status, "llm_rank": 1}]
        if self.mutate_shortlist:
            return [
                {**item, "title": "mutated by LLM", "review_status": status}
                for item in candidates[:limit]
            ]
        return [{**item, "review_status": status, "llm_rank": 1} for item in candidates[:limit]]

    def stage_import(self, candidate: dict[str, Any]) -> str:
        if self.fail_stage:
            raise RuntimeError("staging failed")
        paper_id = str(candidate.get("paper_id") or f"paper-{len(self.staged) + 1}")
        self.staged.append(paper_id)
        self.staged_candidates.append(dict(candidate))
        return paper_id

    def enqueue_analyze(self, paper_id: str) -> None:
        self.analyzed.append(paper_id)

    def draft_projection(self, paper_id: str) -> dict[str, Any]:
        status = "approved" if self.draft_approved else "pending"
        draft = {
            "paper_id": paper_id,
            "review_status": status,
            "paraphrase": "draft",
        }
        self.drafts.append(draft)
        return draft


def _setup(
    *,
    candidates: list[dict[str, Any]],
    policy: DomainPolicy = FINANCE_POLICY,
    records_payload: list[dict[str, Any]] | None = None,
    shortlist_approved: bool = False,
    draft_approved: bool = False,
    fail_stage: bool = False,
    invent_shortlist: bool = False,
    mutate_shortlist: bool = False,
) -> tuple[AcquireCorpusUseCase, FakePaperBridge, NullAcquisitionCycleStore]:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    record_ids: list[str] = []
    for row in records_payload or []:
        records.put(row)
        record_ids.append(str(row["record_id"]))
    snapshots.commit("snap", record_ids, schema_version=1)
    bridge = FakePaperBridge(
        candidates,
        shortlist_approved=shortlist_approved,
        draft_approved=draft_approved,
        fail_stage=fail_stage,
        invent_shortlist=invent_shortlist,
        mutate_shortlist=mutate_shortlist,
    )
    cycles = NullAcquisitionCycleStore()
    promote = PromoteSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        verdicts=NullPolicyVerdictStore(),
        clock=FixedClock(AS_OF),
        policies={policy.policy_id: policy},
    )
    acquire = AcquireCorpusUseCase(
        cycles=cycles,
        promote=promote,
        bridge=bridge,
    )
    return acquire, bridge, cycles


def _search_policy() -> DomainPolicy:
    return replace(
        FINANCE_POLICY,
        expected_cells=frozenset({FIN_CELL}),
        recall_probes=(("probe-a", "doi:10.1/a", "paper"),),
    )


def test_integrity_failure_does_not_search() -> None:
    acquire, bridge, _cycles = _setup(
        candidates=[{"paper_id": "p1", "title": "A"}],
        records_payload=[
            {
                "record_id": "bad",
                "domain_policy_id": "finance/1",
                "type": "paper",
                "paraphrase": "missing source and hash",
            }
        ],
    )
    result = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert result["route"] == "manual"
    assert bridge.discover_calls == 0
    assert result["projected"] is False


def test_searchable_failure_stages_pending_review_idempotently() -> None:
    acquire, bridge, cycles = _setup(
        candidates=[{"paper_id": f"p{i}", "title": f"T{i}"} for i in range(10)],
        policy=_search_policy(),
    )
    first = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert first["route"] == "search"
    assert first["stopped"] == "pending_human_approval"
    assert bridge.discover_calls <= QUERY_BATCH_LIMIT
    assert len(bridge.staged) <= STAGED_IMPORT_LIMIT
    assert bridge.analyzed == bridge.staged
    assert bridge.drafts
    assert all(draft["review_status"] == "pending" for draft in bridge.drafts)
    assert first["projected"] is False
    assert first["state"] == "insufficient"
    cycle_id = first["cycle_id"]

    second = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert second == first
    assert len(bridge.staged) == len(first["staged"])
    assert cycles.get(cycle_id) == first


def test_human_decline_is_explicit_and_does_not_search() -> None:
    acquire, bridge, cycles = _setup(candidates=[], policy=_search_policy())
    result = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
        human_decision="decline",
    )
    assert result["stopped"] == "human_decline"
    assert result["projected"] is False
    assert result["cycle_id"] is not None
    assert bridge.discover_calls == 0
    assert cycles.get(str(result["cycle_id"])) == result


def test_no_candidates_stops_without_claiming_human_decline() -> None:
    acquire, bridge, _cycles = _setup(candidates=[], policy=_search_policy())
    result = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert result["stopped"] == "no_new_candidates"
    assert bridge.discover_calls <= QUERY_BATCH_LIMIT


@pytest.mark.parametrize(
    ("shortlist_approved", "draft_approved"),
    [(True, False), (False, True)],
)
def test_llm_output_cannot_approve_corpus_evidence(
    shortlist_approved: bool,
    draft_approved: bool,
) -> None:
    acquire, _bridge, cycles = _setup(
        candidates=[{"paper_id": "p1", "title": "A"}],
        policy=_search_policy(),
        shortlist_approved=shortlist_approved,
        draft_approved=draft_approved,
    )
    with pytest.raises(ValueError, match="LLM output cannot approve corpus evidence"):
        acquire.run(
            snapshot_id="snap",
            domain_policy_id="finance/1",
            target="calibration",
        )
    stored = next(iter(cycles._rows.values()))
    assert stored["stopped"] == "manual_recovery"


def test_side_effect_failure_leaves_fail_closed_reservation() -> None:
    acquire, bridge, cycles = _setup(
        candidates=[{"paper_id": "p1", "title": "A"}],
        policy=_search_policy(),
        fail_stage=True,
    )
    with pytest.raises(RuntimeError, match="staging failed"):
        acquire.run(
            snapshot_id="snap",
            domain_policy_id="finance/1",
            target="calibration",
        )
    stored = next(iter(cycles._rows.values()))
    assert stored["stopped"] == "manual_recovery"
    discover_calls = bridge.discover_calls

    repeated = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert repeated["stopped"] == "manual_recovery"
    assert bridge.discover_calls == discover_calls


def test_llm_shortlist_cannot_invent_undiscovered_candidate() -> None:
    acquire, _bridge, cycles = _setup(
        candidates=[{"paper_id": "p1", "title": "A"}],
        policy=_search_policy(),
        invent_shortlist=True,
    )
    with pytest.raises(ValueError, match="shortlist candidate was not discovered"):
        acquire.run(
            snapshot_id="snap",
            domain_policy_id="finance/1",
            target="calibration",
        )
    stored = next(iter(cycles._rows.values()))
    assert stored["stopped"] == "manual_recovery"


def test_policy_blocked_snapshot_is_not_reported_sufficient() -> None:
    policy = replace(
        FINANCE_POLICY,
        recall_probes=(("present-probe", "doi:10.1/present", "paper"),),
        expected_cells=frozenset({FIN_CELL}),
        min_records=1,
    )
    acquire, bridge, _cycles = _setup(
        candidates=[],
        policy=policy,
        records_payload=[
            {
                "record_id": "present",
                "domain_policy_id": "finance/1",
                "type": "paper",
                "paraphrase": "present finance evidence",
                "source": "doi:10.1/present",
                "content_hash": "present-hash",
                "coordinates": {
                    "mechanism": "flow-driven",
                    "target": "drawdown",
                    "horizon": "intraday",
                },
            }
        ],
    )
    result = acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )
    assert result["route"] == "stop"
    assert result["state"] == "insufficient"
    assert result["stopped"] == "policy_blocked"
    assert bridge.discover_calls == 0


def test_query_targets_actual_missing_recall_probe() -> None:
    policy = replace(
        FINANCE_POLICY,
        recall_probes=(
            ("present-probe", "doi:10.1/present", "paper"),
            ("missing-probe", "doi:10.1/missing", "paper"),
        ),
    )
    acquire, bridge, _cycles = _setup(
        candidates=[],
        policy=policy,
        records_payload=[
            {
                "record_id": "present",
                "domain_policy_id": "finance/1",
                "type": "paper",
                "paraphrase": "present probe",
                "source": "doi:10.1/present",
                "content_hash": "present-hash",
            }
        ],
    )
    acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert bridge.queries
    assert "missing-probe" in bridge.queries[0]
    assert "present-probe" not in bridge.queries[0]


def test_query_targets_actual_missing_expected_cell() -> None:
    present_cell = FIN_CELL
    missing_cell = "mechanism=behavioral|target=returns|horizon=daily"
    policy = replace(
        FINANCE_POLICY,
        expected_cells=frozenset({present_cell, missing_cell}),
        recall_probes=(("present-probe", "doi:10.1/present", "paper"),),
    )
    acquire, bridge, _cycles = _setup(
        candidates=[],
        policy=policy,
        records_payload=[
            {
                "record_id": "present",
                "domain_policy_id": "finance/1",
                "type": "paper",
                "paraphrase": "present cell",
                "source": "doi:10.1/present",
                "content_hash": "present-hash",
                "coordinates": {
                    "mechanism": "flow-driven",
                    "target": "drawdown",
                    "horizon": "intraday",
                },
            }
        ],
    )
    acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert bridge.queries
    assert missing_cell in bridge.queries[0]
    assert present_cell not in bridge.queries[0]


def test_shortlist_metadata_cannot_mutate_import_candidate() -> None:
    acquire, bridge, _cycles = _setup(
        candidates=[{"paper_id": "p1", "title": "discovered title"}],
        policy=_search_policy(),
        mutate_shortlist=True,
    )
    acquire.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="calibration",
    )
    assert bridge.staged_candidates == [{"paper_id": "p1", "title": "discovered title"}]
