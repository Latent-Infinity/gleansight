from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nsqd.app.use_cases import PromoteSnapshotUseCase
from nsqd.domain.novelty import (
    k_nn_evidence,
    novelty_rank_spearman,
    require_snapshot_state,
    spearman_rho,
)
from nsqd.domain.policy import OPTIMIZATION_POLICY, DomainPolicy
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullPolicyVerdictStore,
)

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
K_VALUES = (3, 5, 10)
BASELINE_K = 5
RHO_THRESHOLD = 0.90
CLUSTER_COUNT = 20
OUTLIER_COUNT = 8
ITEM_COUNT = CLUSTER_COUNT + OUTLIER_COUNT


def _unit(radians: float) -> list[float]:
    return [math.cos(radians), math.sin(radians)]


def _item_vector(index: int) -> list[float]:
    if index < CLUSTER_COUNT:
        return _unit(index * 0.01)
    return _unit(1.2 + (index - CLUSTER_COUNT) * 0.55)


def _calibration_policy() -> DomainPolicy:
    return replace(
        OPTIMIZATION_POLICY,
        recall_probes=(("opt-probe", "doi:10.1/opt-0", "paper"),),
    )


def _promote() -> tuple[
    PromoteSnapshotUseCase,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    DomainPolicy,
]:
    policy = _calibration_policy()
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    use_case = PromoteSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        verdicts=NullPolicyVerdictStore(),
        clock=FixedClock(AS_OF),
        policies={policy.policy_id: policy},
    )
    return use_case, records, snapshots, policy


def _calibration_snapshot() -> tuple[str, NullCorpusIndex, str]:
    use_case, records, snapshots, policy = _promote()
    index = NullCorpusIndex()
    record_ids: list[str] = []
    for index_i in range(ITEM_COUNT):
        record_id = f"opt-{index_i}"
        records.put(
            {
                "record_id": record_id,
                "type": "paper",
                "paraphrase": f"opt method {index_i}",
                "source": f"doi:10.1/opt-{index_i}",
                "content_hash": f"h{index_i}",
                "domain_policy_id": policy.policy_id,
            }
        )
        index.upsert("snap", record_id, _item_vector(index_i))
        record_ids.append(record_id)
    snapshots.commit("snap", record_ids, schema_version=1)
    promoted = use_case.run(
        snapshot_id="snap",
        domain_policy_id=policy.policy_id,
        target="calibration",
    )
    assert promoted["state"] == "calibration"
    return "snap", index, promoted["state"]


def _leave_one_out_distances(index: NullCorpusIndex, snapshot_id: str) -> dict[str, list[float]]:
    distances: dict[str, list[float]] = {}
    for item_index in range(ITEM_COUNT):
        record_id = f"opt-{item_index}"
        allowed = frozenset(f"opt-{other}" for other in range(ITEM_COUNT) if other != item_index)
        hits = index.query(
            snapshot_id,
            _item_vector(item_index),
            k=max(K_VALUES),
            allowed_record_ids=allowed,
        )
        distances[record_id] = [hit.distance for hit in hits]
    return distances


def test_spearman_rho_identical_and_reversed_series() -> None:
    series = [0.1, 0.2, 0.4, 0.7, 1.1]
    assert spearman_rho(series, series) == pytest.approx(1.0)
    assert spearman_rho(series, list(reversed(series))) == pytest.approx(-1.0)
    with pytest.raises(ValueError, match="length mismatch"):
        spearman_rho([1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="at least 2"):
        spearman_rho([1.0], [2.0])
    assert spearman_rho([1.0, 1.0, 2.0], [1.0, 1.0, 3.0]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="undefined for constant ranks"):
        spearman_rho([0.0, 0.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="undefined for constant ranks"):
        spearman_rho([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])


def test_k_nn_evidence_uses_first_k_distances() -> None:
    distances = [0.10, 0.20, 0.30, 0.40, 0.50]
    assert k_nn_evidence(distances, 3) == pytest.approx(0.20)
    assert k_nn_evidence(distances, 5) == pytest.approx(0.30)
    assert k_nn_evidence([], 5) is None
    with pytest.raises(ValueError, match="k must be"):
        k_nn_evidence(distances, 0)


def test_novelty_rank_spearman_rejects_smoke_only() -> None:
    with pytest.raises(ValueError, match="calibration"):
        novelty_rank_spearman(
            item_distances={"a": [0.1, 0.2, 0.3], "b": [0.2, 0.3, 0.4]},
            k_values=K_VALUES,
            baseline_k=BASELINE_K,
            snapshot_state="smoke_only",
        )
    assert require_snapshot_state("calibration") == "calibration"
    with pytest.raises(ValueError, match="at least 2"):
        novelty_rank_spearman(
            item_distances={"a": [0.1, 0.2, 0.3]},
            k_values=K_VALUES,
            baseline_k=BASELINE_K,
            snapshot_state="calibration",
        )


def test_novelty_rank_spearman_requires_complete_neighbor_evidence() -> None:
    with pytest.raises(ValueError, match="needs at least 5 distances for a"):
        novelty_rank_spearman(
            item_distances={"a": [], "b": [0.1, 0.2, 0.3, 0.4, 0.5]},
            k_values=(3, 5),
            baseline_k=5,
            snapshot_state="calibration",
        )


def test_alg_k_spearman_vs_baseline_on_calibration_snapshot() -> None:
    snapshot_id, index, snapshot_state = _calibration_snapshot()
    distances = _leave_one_out_distances(index, snapshot_id)
    correlations = novelty_rank_spearman(
        item_distances=distances,
        k_values=K_VALUES,
        baseline_k=BASELINE_K,
        snapshot_state=snapshot_state,
    )
    assert set(correlations) == set(K_VALUES)
    assert correlations[BASELINE_K] == pytest.approx(1.0)
    assert correlations[3] >= RHO_THRESHOLD
    assert correlations[10] < RHO_THRESHOLD


def test_alg_k_artifact_records_math_probe_without_freeze() -> None:
    text = Path("docs/ablations/alg-k.md").read_text(encoding="utf-8")
    assert "Freeze: no" in text
    assert "DATA-NSQD-03" in text
    assert "ρ" in text or "rho" in text.lower()
