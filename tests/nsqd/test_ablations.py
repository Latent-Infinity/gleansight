from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from nsqd.app.use_cases import PromoteSnapshotUseCase
from nsqd.domain.ablation import (
    AXIS_KEEP_SUM,
    DENSITY_CUTS,
    density_cut_agreement,
    keep_axis_triple,
    labeled_status_cells,
    proposed_axis_triples,
    select_density_cut,
    viability_keeps_presence_stubs,
)
from nsqd.domain.novelty import novelty_term
from nsqd.domain.policy import OPTIMIZATION_POLICY
from nsqd.domain.status import cell_status
from nsqd.domain.viability import score_dpred, score_fals, score_mech
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullPolicyVerdictStore,
)

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
RECENT = AS_OF - timedelta(days=10)
NSQD_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"


def _load_card(name: str) -> dict[object, object]:
    payload = yaml.safe_load((NSQD_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_keep_axis_triple_uses_sum_threshold() -> None:
    assert keep_axis_triple((2, 2, 2)) is True
    assert keep_axis_triple((2, 2, 0)) is True
    assert keep_axis_triple((1, 2, 0)) is False
    assert AXIS_KEEP_SUM == 4
    with pytest.raises(ValueError, match="0-2"):
        keep_axis_triple((3, 0, 0))
    with pytest.raises(ValueError, match="exactly 3"):
        keep_axis_triple((2, 2))
    with pytest.raises(ValueError, match="exactly 3"):
        keep_axis_triple((2, 2, 0, 0))


def test_alg_axes_keeps_finance_triple_only() -> None:
    kept = [triple.axis_id for triple in proposed_axis_triples() if keep_axis_triple(triple.scores)]
    assert kept == ["finance-v1-mechanism-target-horizon"]


def test_density_cut_parameter_shifts_sparse_and_active() -> None:
    records = [
        {"type": "paper", "harvested_at": RECENT},
        {"type": "code", "harvested_at": RECENT},
    ]
    kwargs = {
        "as_of": AS_OF,
        "snapshot_state": "calibration",
        "inspected": True,
        "expected": False,
    }
    assert cell_status(records, density_cut=2, **kwargs) == "Active"
    assert cell_status(records, density_cut=3, **kwargs) == "Sparse"
    assert cell_status(records, density_cut=5, **kwargs) == "Sparse"
    with pytest.raises(ValueError, match="density_cut"):
        cell_status(records, density_cut=1, **kwargs)


def test_alg_status_thresholds_keep_default_cut() -> None:
    cases = labeled_status_cells(as_of=AS_OF)
    assert len(cases) == 10
    agreements = density_cut_agreement(cases, as_of=AS_OF)
    assert set(agreements) == set(DENSITY_CUTS)
    chosen = select_density_cut(agreements)
    assert chosen == 3
    assert agreements[3] >= 8
    assert agreements[3] == max(agreements.values())


def test_viability_keeps_presence_stubs() -> None:
    assert viability_keeps_presence_stubs() is True
    filled = {
        "mechanism": "x",
        "inefficiency": "x",
        "counterparty": "x",
        "persistence": "x",
        "capacity": "x",
        "regime_dependence": "x",
        "cheapest_falsifier": "x",
        "kill_criteria": "x",
        "differential_prediction": "x",
    }
    assert score_mech(filled, domain_pack="finance/1") == 5
    assert score_fals(filled) == 5
    assert score_dpred(filled) == 5
    empty = dict.fromkeys(filled, "")
    assert score_mech(empty, domain_pack="finance/1") == 0
    assert score_fals(empty) == 0
    assert score_dpred(empty) == 0
    assert score_mech(filled, domain_pack="optimization/1") == 0


def test_alg_novelty_bins_on_calibration_pair() -> None:
    gamma = _load_card("gamma-flow.yaml")
    mechanism_free = _load_card("mechanism-free.yaml")
    policy = replace(
        OPTIMIZATION_POLICY,
        recall_probes=(("opt-probe", "doi:10.1/opt-0", "paper"),),
    )
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    index = NullCorpusIndex()
    records.put(
        {
            "record_id": "opt-0",
            "type": "paper",
            "paraphrase": "opt method 0",
            "source": "doi:10.1/opt-0",
            "content_hash": "h0",
            "domain_policy_id": policy.policy_id,
        }
    )
    index.upsert("snap", "opt-0", [1.0, 0.0])
    snapshots.commit("snap", ["opt-0"], schema_version=1)
    promoted = PromoteSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        verdicts=NullPolicyVerdictStore(),
        clock=FixedClock(AS_OF),
        policies={policy.policy_id: policy},
    ).run(
        snapshot_id="snap",
        domain_policy_id=policy.policy_id,
        target="calibration",
    )
    assert promoted["state"] == "calibration"
    hits = index.query("snap", [1.0, 0.0], k=5)
    evidence = sum(hit.distance for hit in hits) / len(hits)
    nov = novelty_term(
        evidence=evidence,
        snapshot_state="calibration",
        grounding_class="orthogonal",
    )
    assert nov >= 1
    assert score_mech(mechanism_free, domain_pack="finance/1") == 0
    assert (
        novelty_term(
            evidence=evidence,
            snapshot_state="smoke_only",
            grounding_class="orthogonal",
        )
        == 0
    )
    assert gamma["id"] == "gamma-flow-dealer-convexity"


def test_select_density_cut_errors_and_tie_break() -> None:
    with pytest.raises(ValueError, match="empty"):
        select_density_cut({})
    with pytest.raises(ValueError, match="8/10"):
        select_density_cut({2: 7, 3: 6, 5: 5})
    assert select_density_cut({2: 9, 5: 9}) == 2


def test_ablation_artifacts_are_llm_probes_not_frozen() -> None:
    root = Path("docs/ablations")
    for name in (
        "alg-axes.md",
        "alg-status.md",
        "alg-viability.md",
        "alg-novelty-bins.md",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert "Freeze: no" in text
        assert "Prompt" in text
