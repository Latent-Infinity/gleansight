from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nsqd.app.use_cases import PromoteSnapshotUseCase, RankArchiveUseCase
from nsqd.domain.coverage import RankGuardBlocked
from nsqd.domain.policy import FINANCE_POLICY, OPTIMIZATION_POLICY, DomainPolicy, verdict_key
from nsqd.domain.project import (
    PROJECTOR_VERSION,
    canonical_reviewed_projection_digest,
    normalize_paraphrase,
    projection_record_id,
)
from nsqd.domain.snapshot import record_content_hash, sha256_hex
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullPolicyVerdictStore,
)

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
OPT_CELL = "problem=constrained-expectation|method=sequential-quadratic|setting=rank-deficient"


def _promote(
    policies: dict[str, DomainPolicy] | None = None,
    approved_harvest_seed_digests: frozenset[str] = frozenset(),
) -> tuple[PromoteSnapshotUseCase, NullCorpusRecordStore, NullCorpusSnapshotStore]:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    use_case = PromoteSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        verdicts=NullPolicyVerdictStore(),
        clock=FixedClock(AS_OF),
        policies=policies,
        approved_harvest_seed_digests=approved_harvest_seed_digests,
    )
    return use_case, records, snapshots


def test_same_snapshot_holds_independent_policy_verdicts() -> None:
    finance_policy = replace(
        FINANCE_POLICY,
        recall_probes=(("fin", "doi:10.1/fin", "paper"),),
        expected_cells=frozenset({"mechanism=flow-driven|target=drawdown|horizon=intraday"}),
        min_records=1,
    )
    optimization_policy = replace(
        OPTIMIZATION_POLICY,
        recall_probes=(("opt-probe", "doi:10.1/opt", "paper"),),
        expected_cells=frozenset({OPT_CELL}),
    )
    use_case, records, snapshots = _promote(
        {
            finance_policy.policy_id: finance_policy,
            optimization_policy.policy_id: optimization_policy,
        }
    )
    records.put(
        {
            "record_id": "opt",
            "type": "paper",
            "paraphrase": "opt method",
            "source": "doi:10.1/opt",
            "content_hash": "h1",
            "domain_policy_id": "optimization/1",
            "coordinates": {
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
        }
    )
    snapshots.commit("snap", ["opt"], schema_version=1)
    finance = use_case.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )
    optimization = use_case.run(
        snapshot_id="snap",
        domain_policy_id="optimization/1",
        target="calibration",
    )
    assert finance["key"] == verdict_key(snapshot_id="snap", domain_policy_id="finance/1")
    assert optimization["key"] == verdict_key(snapshot_id="snap", domain_policy_id="optimization/1")
    assert finance["state"] == "insufficient"
    assert "recall_probe_missing" in finance["failures"]
    assert optimization["state"] == "calibration"
    assert finance["key"] != optimization["key"]


def test_finance_production_valid_blocked_without_harvest_seed() -> None:
    use_case, _records, snapshots = _promote()
    snapshots.commit("snap", [], schema_version=1)
    result = use_case.run(
        snapshot_id="snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )
    assert result["state"] == "insufficient"


def test_rank_guard_does_not_promote_or_acquire() -> None:
    with pytest.raises(RankGuardBlocked, match="rank_guard_blocked"):
        RankArchiveUseCase(cell_statuses={}, domain_policy_id="optimization/1").run(
            elite_cell_ids=set()
        )


def _production_policy(source_paper_id: str = "finance-seed") -> DomainPolicy:
    return replace(
        FINANCE_POLICY,
        expected_cells=frozenset({"mechanism=flow-driven|target=drawdown|horizon=intraday"}),
        recall_probes=(("finance-seed", f"paper:{source_paper_id}", "paper"),),
        min_records=1,
    )


def _projected_seed(
    *,
    source_paper_id: str = "finance-seed",
    paraphrase: str = "approved finance mechanism",
) -> tuple[dict[str, object], str]:
    normalized_paraphrase = normalize_paraphrase(paraphrase)
    row: dict[str, object] = {
        "type": "paper",
        "paraphrase": normalized_paraphrase,
        "source": f"paper:{source_paper_id}",
        "domain_policy_id": "finance/1",
        "coordinates": {
            "mechanism": "flow-driven",
            "target": "drawdown",
            "horizon": "intraday",
        },
        "review_status": "approved",
        "human_reviewer": "reviewer@example.com",
        "human_approved_at": AS_OF.isoformat(),
        "paraphrase_source": "human-reviewed mechanism summary",
        "source_paper_id": source_paper_id,
        "source_abstract_sha256": "1" * 64,
        "source_markdown_sha256": "2" * 64,
        "paraphrase_sha256": sha256_hex(normalized_paraphrase.encode("utf-8")),
        "projector_version": PROJECTOR_VERSION,
    }
    row["record_id"] = projection_record_id(row)
    row["content_hash"] = record_content_hash(
        type="paper",
        paraphrase=normalized_paraphrase,
        source=str(row["source"]),
    )
    digest = canonical_reviewed_projection_digest(row)
    row["reviewed_projection_digest"] = digest
    return row, digest


def test_finance_production_valid_requires_trusted_projected_seed() -> None:
    row, digest = _projected_seed()
    policy = _production_policy()
    use_case, records, snapshots = _promote(
        {policy.policy_id: policy},
        frozenset({digest}),
    )
    records.put(row)
    snapshots.commit("finance-snap", [str(row["record_id"])], schema_version=1)

    result = use_case.run(
        snapshot_id="finance-snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )

    assert result["state"] == "production_valid"


def test_approval_shaped_row_without_trusted_digest_cannot_unlock_production() -> None:
    row, _digest = _projected_seed(source_paper_id="untrusted-finance-seed")
    row.pop("reviewed_projection_digest")
    policy = _production_policy("untrusted-finance-seed")
    use_case, records, snapshots = _promote({policy.policy_id: policy})
    records.put(row)
    snapshots.commit("untrusted-finance-snap", [str(row["record_id"])], schema_version=1)

    result = use_case.run(
        snapshot_id="untrusted-finance-snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )

    assert result["state"] == "insufficient"


def test_invalid_human_approved_record_cannot_unlock_finance_production() -> None:
    row, digest = _projected_seed(source_paper_id="invalid-finance-seed")
    row["invalid_reason"] = "failed integrity review"
    policy = _production_policy("invalid-finance-seed")
    use_case, records, snapshots = _promote({policy.policy_id: policy}, frozenset({digest}))
    records.put(row)
    snapshots.commit("invalid-finance-snap", [str(row["record_id"])], schema_version=1)

    result = use_case.run(
        snapshot_id="invalid-finance-snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )

    assert result["state"] == "insufficient"


def test_retracted_trusted_record_cannot_unlock_finance_production() -> None:
    row, digest = _projected_seed(source_paper_id="retracted-finance-seed")
    row["retracted"] = True
    policy = _production_policy("retracted-finance-seed")
    use_case, records, snapshots = _promote({policy.policy_id: policy}, frozenset({digest}))
    records.put(row)
    snapshots.commit("retracted-finance-snap", [str(row["record_id"])], schema_version=1)

    result = use_case.run(
        snapshot_id="retracted-finance-snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )

    assert result["state"] == "insufficient"


def test_trusted_seed_cannot_unlock_incomplete_finance_manifest() -> None:
    row, digest = _projected_seed(source_paper_id="trusted-but-unconfigured")
    incomplete_policy = replace(
        FINANCE_POLICY,
        expected_cells=frozenset(),
        recall_probes=(),
        required_record_types={"paper": 0, "code": 0, "benchmark": 0},
        min_records=0,
    )
    use_case, records, snapshots = _promote({"finance/1": incomplete_policy}, frozenset({digest}))
    records.put(row)
    snapshots.commit("trusted-unconfigured-snap", [str(row["record_id"])], schema_version=1)

    result = use_case.run(
        snapshot_id="trusted-unconfigured-snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )

    assert result["state"] == "insufficient"
    assert "manifest_missing" in result["failures"]


def test_trusted_digest_replay_on_mutated_projection_cannot_unlock_production() -> None:
    row, digest = _projected_seed(source_paper_id="mutated-finance-seed")
    row["paraphrase"] = "forged mechanism after approval"
    policy = _production_policy("mutated-finance-seed")
    use_case, records, snapshots = _promote({policy.policy_id: policy}, frozenset({digest}))
    records.put(row)
    snapshots.commit("mutated-finance-snap", [str(row["record_id"])], schema_version=1)

    result = use_case.run(
        snapshot_id="mutated-finance-snap",
        domain_policy_id="finance/1",
        target="production_valid",
    )

    assert result["state"] == "insufficient"
