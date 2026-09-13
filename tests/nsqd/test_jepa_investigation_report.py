from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from papers.domain import (
    ClaimKind,
    ComparisonScope,
    CompletenessAssessment,
    EvidenceStatus,
    InvestigationPlan,
    InvestigationPlanValidationContext,
    OutputValidationFailed,
    StepStatus,
    parse_investigation_plan_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCRIPT = REPO_ROOT / "scripts" / "report_jepa_ideas_gaps.py"


def _load_report_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("jepa_investigation_report_test", REPORT_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"expected importable script: {REPORT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_plan() -> InvestigationPlan:
    report = _load_report_script()
    results = report._read_packet_json("results.json")
    ledger = report._read_packet_json("source-ledger.json")
    prior_art = report._read_packet_json("operator-e-broader-prior-art.json")
    return report._build_investigation_plan(results, ledger, prior_art)


def test_jepa_builder_emits_baseline_and_three_typed_directions() -> None:
    plan = _build_plan()
    baseline = plan.baseline_replication

    assert plan.question == (
        "What must be reproduced from Fin-JEPA before testing calibrated uncertainty, "
        "event-conditioned relevance gating, or raw-plus-denoised dual targets?"
    )
    assert baseline.strategy.value == "constrained_reproduction"
    assert baseline.information_completeness.assessment is CompletenessAssessment.incomplete
    assert baseline.information_completeness.source_refs == ("N11-FIN-01",)
    assert baseline.protocol_equivalence.evidence_status is EvidenceStatus.unknown
    assert baseline.protocol_equivalence.value is None
    assert baseline.protocol_equivalence.source_refs == ("N11-FIN-01",)
    assert baseline.metric_comparability.evidence_status is EvidenceStatus.unknown
    assert baseline.metric_comparability.value is None
    assert baseline.comparison_scope is ComparisonScope.no_direct_comparison
    assert baseline.missing_information
    assert len(baseline.steps) == 4
    assert len(plan.directions) == 3
    assert all(direction.replication_steps for direction in plan.directions)
    assert all(direction.assumptions for direction in plan.directions)


def test_jepa_source_titles_match_retained_metadata_for_every_returned_source() -> None:
    report = _load_report_script()
    ledger = report._read_packet_json("source-ledger.json")
    prior_art = report._read_packet_json("operator-e-broader-prior-art.json")
    retained_titles = {
        **{str(row["record_id"]): str(row["title"]) for row in ledger["records"]},
        **{str(row["stable_id"]): str(row["title"]) for row in prior_art["primary_sources"]},
    }
    plan = _build_plan()
    expected_ids = (
        "N11-FIN-01",
        "arXiv:2507.05470",
        "N11-FIN-02",
        "arXiv:2605.28520",
        "N11-FIN-05",
    )

    assert tuple((source.paper_id, source.title) for source in plan.sources) == tuple(
        (source_id, retained_titles[source_id]) for source_id in expected_ids
    )


def test_jepa_constrained_reproduction_records_concrete_proposed_substitutions() -> None:
    baseline = _build_plan().baseline_replication

    assert len(baseline.deviations) >= 3
    assert all(deviation.claim_kind is ClaimKind.proposal for deviation in baseline.deviations)
    assert all(
        deviation.evidence_status is EvidenceStatus.proposed for deviation in baseline.deviations
    )
    assert all(deviation.value is not None for deviation in baseline.deviations)
    assert all(deviation.uncertainty_rationale is not None for deviation in baseline.deviations)


def test_jepa_report_preserves_retained_experiment_contracts() -> None:
    report = _load_report_script()
    results = report._read_packet_json("results.json")
    ledger = report._read_packet_json("source-ledger.json")
    prior_art = report._read_packet_json("operator-e-broader-prior-art.json")

    data = report._build_report_data(results, ledger, prior_art)
    retained = {row["hypothesis_id"]: row for row in data["retained_hypotheses"]}
    for source in results["proposed_ideas"]:
        experiment = retained[source["candidate_id"]]["experiment"]
        source_test = source["falsifiable_test"]
        assert experiment["baselines"] == source_test["design"]
        assert experiment["primary_metric"] == source_test["primary_metric"]
        assert experiment["secondary_metrics"] == tuple(source_test["secondary_metrics"])
        assert experiment["reject_condition"] == source_test["failure_condition"]


def test_jepa_directions_keep_sources_with_their_supported_mechanisms() -> None:
    plan = _build_plan()
    expected_refs = (
        {"N11-FIN-01", "arXiv:2507.05470"},
        {"N11-FIN-01", "N11-FIN-02", "arXiv:2605.28520"},
        {"N11-FIN-01", "N11-FIN-05"},
    )

    for direction, allowed_refs in zip(plan.directions, expected_refs, strict=True):
        payload = direction.model_dump(mode="json")
        cited_refs = {
            ref
            for section in (payload["data"], payload["model"])
            for statement in section.values()
            for ref in statement["source_refs"]
        }
        cited_refs.update(direction.compute.hardware.source_refs)
        cited_refs.update(
            ref for assumption in direction.assumptions for ref in assumption.source_refs
        )
        assert cited_refs <= allowed_refs
        assert plan.baseline_replication.core_paper_ref in cited_refs


def test_jepa_plan_marks_unmeasured_compute_and_unexecuted_work_truthfully() -> None:
    plan = _build_plan()

    for direction in plan.directions:
        assert direction.data.access.value is None
        assert direction.data.license.value is None
        assert direction.compute.feasibility_tier.value == "unknown"
        assert direction.compute.hardware.value is None
        assert direction.compute.vram_gb.value is None
        assert direction.compute.vram_gb.basis is None
        assert direction.compute.gpu_hours.value is None
        assert direction.compute.gpu_hours.basis is None
    all_steps = [
        *plan.baseline_replication.steps,
        *(step for direction in plan.directions for step in direction.replication_steps),
    ]
    assert {step.status for step in all_steps} <= {StepStatus.not_started, StepStatus.blocked}
    assert all(step.evidence_refs == () for step in all_steps)
    assert all(
        (step.blocked_reason is not None) is (step.status is StepStatus.blocked)
        for step in all_steps
    )


def test_jepa_plan_round_trip_rejects_omission() -> None:
    plan = _build_plan()
    payload = plan.model_dump(mode="json")
    allowed_sources = frozenset(source.paper_id for source in plan.sources)

    parsed = parse_investigation_plan_json(
        json.dumps(payload),
        InvestigationPlanValidationContext(
            expected_question=plan.question,
            allowed_source_ids=allowed_sources,
            allowed_execution_evidence_refs=frozenset(),
        ),
    )
    del payload["directions"][0]["compute"]

    assert parsed == plan
    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(payload)


def test_jepa_plan_rejects_misattributed_unknown_source() -> None:
    plan = _build_plan()
    payload = plan.model_dump(mode="json")
    allowed_sources = frozenset(source.paper_id for source in plan.sources)
    payload["directions"][1]["model"]["architecture"]["source_refs"].append("N11-FIN-04")

    with pytest.raises(OutputValidationFailed):
        parse_investigation_plan_json(
            json.dumps(payload),
            InvestigationPlanValidationContext(
                expected_question=plan.question,
                allowed_source_ids=allowed_sources,
                allowed_execution_evidence_refs=frozenset(),
            ),
        )
