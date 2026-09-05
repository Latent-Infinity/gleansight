from __future__ import annotations

from pathlib import Path

import pytest

from nsqd.app.handlers import NsqdHandlerContext, handle_diverge
from nsqd.app.use_cases import DivergeUseCase
from nsqd.composition import build_container
from nsqd.domain.diverge import (
    DEFAULT_ENABLED_OPERATORS,
    require_enabled_operators,
    require_operator,
)
from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU
from nsqd.domain.operator_e import (
    OPERATOR_E_ALGORITHM_IDENTITY,
    OPERATOR_E_ATYPICALITY_INTERPRETATION,
    require_operator_e_combination,
)
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
from tests.nsqd.test_operator_a import AS_OF, MISSING, _finance_statuses

ENABLED_OPERATORS = frozenset({"A", "E"})
SNAPSHOT_ID = "8" * 64
MISSING_DESCRIPTOR = {
    "mechanism": "behavioral",
    "target": "returns",
    "horizon": "daily",
}
BRIDGE = (
    "Replace point latent prediction with a calibrated latent distribution "
    "and use context-only regime strata to test whether uncertainty supports abstention."
)


def _component(record_id: str, *, domain_policy_id: str) -> dict[str, object]:
    return {
        "id": record_id,
        "kind": "corpus-paper-paraphrase",
        "review_status": "approved",
        "domain_policy_id": domain_policy_id,
    }


def _candidate(**overrides: object) -> dict[str, object]:
    candidate: dict[str, object] = {
        "title": "calibrated latent-distribution combination",
        "domain_policy_id": "finance/1",
        "research_descriptor": MISSING_DESCRIPTOR,
        "combination_track": "same_policy",
        "components": [
            _component("N11-FIN-01", domain_policy_id="finance/1"),
            _component("N11-FIN-04", domain_policy_id="finance/1"),
        ],
        "mechanistic_bridge": BRIDGE,
        "atypicality": {"interpretation": OPERATOR_E_ATYPICALITY_INTERPRETATION, "score": 1.0},
        "nearest_prior_combinations": [],
        "co_occurrence_snapshot_id": SNAPSHOT_ID,
    }
    candidate.update(overrides)
    return candidate


def _enabled_use_case(*, candidates: NullNsqdCandidateStore | None = None) -> DivergeUseCase:
    return DivergeUseCase(
        candidates=candidates or NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        clock=FixedClock(AS_OF),
        enabled_operators=ENABLED_OPERATORS,
    )


def _handler_context(*, enabled_operators: frozenset[str]) -> NsqdHandlerContext:
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
        enabled_operators=enabled_operators,
    )


def _operator_e_job() -> NsqdJob:
    return NsqdJob(
        job_id="job-e",
        type="diverge",
        status="running",
        payload={
            "candidate": _candidate(),
            "generator_run_id": "gen-e",
            "axioms": [{"statement": "combine approved components", "cell_id": MISSING}],
            "operator": "E",
            "target_cell_id": MISSING,
            "cell_statuses": _finance_statuses({MISSING: "Missing"}),
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )


def test_require_operator_e_combination_accepts_same_policy_bridge() -> None:
    bound = require_operator_e_combination(_candidate())
    assert bound["combination_track"] == "same_policy"
    assert bound["component_ids"] == ["N11-FIN-01", "N11-FIN-04"]
    assert bound["mechanistic_bridge"] == BRIDGE
    assert bound["algorithm_identity"] == OPERATOR_E_ALGORITHM_IDENTITY


def test_require_operator_e_combination_rejects_rarity_only_and_unapproved_components() -> None:
    with pytest.raises(ValueError, match="rarity-only"):
        require_operator_e_combination(_candidate(generation_method="rarity_only_negative_control"))
    with pytest.raises(ValueError, match="rarity-only"):
        require_operator_e_combination(_candidate(mechanistic_bridge="low co-occurrence"))
    with pytest.raises(ValueError, match="at least two"):
        require_operator_e_combination(
            _candidate(components=[_component("N11-FIN-01", domain_policy_id="finance/1")])
        )
    with pytest.raises(ValueError, match="requirement-card"):
        require_operator_e_combination(
            _candidate(
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    {
                        "id": "DATA-NSQD-01",
                        "kind": "candidate-requirement-card",
                        "review_status": "approved",
                        "domain_policy_id": "finance/1",
                    },
                ]
            )
        )
    with pytest.raises(ValueError, match="must be approved"):
        require_operator_e_combination(
            _candidate(
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    {
                        "id": "N11-FIN-04",
                        "kind": "corpus-paper-paraphrase",
                        "review_status": "pending",
                        "domain_policy_id": "finance/1",
                    },
                ]
            )
        )


def test_require_operator_e_combination_rejects_malformed_tracks_and_components() -> None:
    with pytest.raises(ValueError, match="combination_track must be same_policy or cross_policy"):
        require_operator_e_combination(_candidate(combination_track="pooled"))
    with pytest.raises(ValueError, match="not an E track policy"):
        require_operator_e_combination(_candidate(domain_policy_id="biology/1"))
    with pytest.raises(ValueError, match="components is required"):
        require_operator_e_combination(_candidate(components="N11-FIN-01"))
    with pytest.raises(ValueError, match="must be unique"):
        require_operator_e_combination(
            _candidate(
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                ]
            )
        )
    with pytest.raises(ValueError, match="approved paraphrases"):
        require_operator_e_combination(
            _candidate(
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    {
                        "id": "N11-FIN-04",
                        "kind": "essay",
                        "review_status": "approved",
                        "domain_policy_id": "finance/1",
                    },
                ]
            )
        )
    with pytest.raises(ValueError, match="component domain_policy_id is not an E track policy"):
        require_operator_e_combination(
            _candidate(
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    _component("N11-FIN-04", domain_policy_id="biology/1"),
                ]
            )
        )
    with pytest.raises(ValueError, match="canonical rarity contract"):
        require_operator_e_combination(
            _candidate(atypicality={"interpretation": "novelty and value", "score": 1.0})
        )
    with pytest.raises(ValueError, match="nearest_prior_combinations is required"):
        require_operator_e_combination(_candidate(nearest_prior_combinations="none"))
    with pytest.raises(ValueError, match="source_domain_policy_id is not an E track policy"):
        require_operator_e_combination(
            _candidate(
                combination_track="cross_policy",
                source_domain_policy_id="biology/1",
                components=[
                    _component("N11-OPT-01", domain_policy_id="optimization/1"),
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                ],
                co_occurrence_snapshot_id=None,
            )
        )
    with pytest.raises(ValueError, match="distinct source and target"):
        require_operator_e_combination(
            _candidate(
                combination_track="cross_policy",
                source_domain_policy_id="finance/1",
                components=[
                    _component("N11-OPT-01", domain_policy_id="optimization/1"),
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                ],
                co_occurrence_snapshot_id=None,
            )
        )
    bound = require_operator_e_combination(
        _candidate(
            combination_track="cross_policy",
            source_domain_policy_id="optimization/1",
            components=[
                _component("N11-OPT-01", domain_policy_id="optimization/1"),
                _component("N11-FIN-01", domain_policy_id="finance/1"),
            ],
            co_occurrence_snapshot_id=SNAPSHOT_ID,
        )
    )
    assert bound["co_occurrence_snapshot_id"] == SNAPSHOT_ID


def test_require_operator_e_combination_keeps_tracks_unpooled() -> None:
    with pytest.raises(ValueError, match="same_policy"):
        require_operator_e_combination(
            _candidate(
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    _component("N11-OPT-01", domain_policy_id="optimization/1"),
                ]
            )
        )
    cross = require_operator_e_combination(
        _candidate(
            combination_track="cross_policy",
            source_domain_policy_id="optimization/1",
            components=[
                _component("N11-OPT-01", domain_policy_id="optimization/1"),
                _component("N11-FIN-01", domain_policy_id="finance/1"),
            ],
            co_occurrence_snapshot_id=None,
        )
    )
    assert cross["combination_track"] == "cross_policy"
    assert cross["source_domain_policy_id"] == "optimization/1"
    with pytest.raises(ValueError, match="cross_policy"):
        require_operator_e_combination(
            _candidate(
                combination_track="cross_policy",
                source_domain_policy_id="optimization/1",
                components=[
                    _component("N11-FIN-01", domain_policy_id="finance/1"),
                    _component("N11-FIN-04", domain_policy_id="finance/1"),
                ],
                co_occurrence_snapshot_id=None,
            )
        )


def test_default_composition_rejects_operator_e_independent_of_tau() -> None:
    assert NOVELTY_THRESHOLD_TAU == 0.45
    with pytest.raises(ValueError, match="not enabled by composition"):
        require_operator("E")
    assert require_operator("E", enabled_operators=ENABLED_OPERATORS) == "E"


def test_allowlisted_diverge_persists_operator_e_without_inverting_axioms() -> None:
    candidates = NullNsqdCandidateStore()
    digest = _enabled_use_case(candidates=candidates).run(
        candidate=_candidate(),
        generator_run_id="gen-e",
        axioms=[{"statement": "combine approved components", "cell_id": MISSING}],
        operator="E",
        target_cell_id=MISSING,
        cell_statuses=_finance_statuses({MISSING: "Missing"}),
    )
    stored = candidates.get_artifact(digest)
    assert stored is not None
    assert stored["operator"] == "E"
    assert stored["target_cell_id"] == MISSING
    assert stored["candidate"]["mechanistic_bridge"] == BRIDGE
    assert stored["candidate"]["combination_track"] == "same_policy"


def test_allowlisted_diverge_requires_operator_e_target_occupancy() -> None:
    with pytest.raises(ValueError, match="Operator E requires an ALG-SEL target"):
        _enabled_use_case().run(
            candidate=_candidate(),
            generator_run_id="gen-e",
            axioms=[{"statement": "combine approved components"}],
            operator="E",
        )
    with pytest.raises(
        ValueError, match="research_descriptor must resolve to the Operator E target"
    ):
        _enabled_use_case().run(
            candidate=_candidate(
                research_descriptor={
                    "mechanism": "flow-driven",
                    "target": "drawdown",
                    "horizon": "intraday",
                }
            ),
            generator_run_id="gen-e",
            axioms=[{"statement": "combine approved components", "cell_id": MISSING}],
            operator="E",
            target_cell_id=MISSING,
            cell_statuses=_finance_statuses({MISSING: "Missing"}),
        )


def test_allowlisted_diverge_rejects_rarity_only_operator_e() -> None:
    with pytest.raises(ValueError, match="rarity-only"):
        _enabled_use_case().run(
            candidate=_candidate(generation_method="rarity_only_negative_control"),
            generator_run_id="gen-e",
            axioms=[{"statement": "combine approved components", "cell_id": MISSING}],
            operator="E",
            target_cell_id=MISSING,
            cell_statuses=_finance_statuses({MISSING: "Missing"}),
        )
    with pytest.raises(ValueError, match="Operator E cannot invert axioms"):
        _enabled_use_case().run(
            candidate=_candidate(inversion=True),
            generator_run_id="gen-e",
            axioms=[{"statement": "combine approved components", "cell_id": MISSING}],
            operator="E",
            target_cell_id=MISSING,
            cell_statuses=_finance_statuses({MISSING: "Missing"}),
        )


def test_handler_job_cannot_widen_composition_to_operator_e() -> None:
    default_ctx = _handler_context(enabled_operators=frozenset({"A"}))
    with pytest.raises(ValueError, match="not enabled by composition"):
        handle_diverge(default_ctx, _operator_e_job())
    enabled_ctx = _handler_context(enabled_operators=ENABLED_OPERATORS)
    result = handle_diverge(enabled_ctx, _operator_e_job())
    stored = enabled_ctx.candidates.get_artifact(result["candidate_artifact_hash"])
    assert stored is not None
    assert stored["operator"] == "E"


def test_require_enabled_operators_may_add_experimental_e() -> None:
    assert require_enabled_operators(None) == DEFAULT_ENABLED_OPERATORS
    assert require_enabled_operators(["A", "E"]) == frozenset({"A", "E"})
    assert require_enabled_operators(["A", "B", "E"]) == frozenset({"A", "B", "E"})
    with pytest.raises(ValueError, match="operator C is not supported"):
        require_enabled_operators({"A", "C", "E"})


def test_container_defaults_omit_e_and_config_can_add_e(tmp_path: Path) -> None:
    default_container = build_container(
        db_path=tmp_path / "default.sqlite",
        index_path=tmp_path / "default-index",
    )
    assert default_container.ctx.enabled_operators == DEFAULT_ENABLED_OPERATORS
    assert "E" not in default_container.ctx.enabled_operators
    enabled = build_container(
        db_path=tmp_path / "enabled.sqlite",
        index_path=tmp_path / "enabled-index",
        enabled_operators=ENABLED_OPERATORS,
    )
    assert enabled.ctx.enabled_operators == ENABLED_OPERATORS
