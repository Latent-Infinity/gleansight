from __future__ import annotations

from typing import Any

from papers.domain import (
    DataRequirements,
    EvidenceStatement,
    InvestigationDirection,
    ModelRequirements,
    ReplicationStep,
    StepStatus,
)
from scripts._jepa_plan_values import (
    operational_assumptions,
    proposed,
    reported,
    unknown,
    unknown_compute,
)

CORE_REF = "N11-FIN-01"
CALIBRATION_REF = "arXiv:2507.05470"
CET_REF = "N11-FIN-02"
GATE_REF = "arXiv:2605.28520"
DENOISING_REF = "N11-FIN-05"


def _blocked_step(description: str, reason: str) -> ReplicationStep:
    return ReplicationStep(
        description=description,
        status=StepStatus.blocked,
        evidence_refs=(),
        blocked_reason=reason,
    )


def _experiment_steps(idea: dict[str, Any], mechanism_step: str) -> tuple[ReplicationStep, ...]:
    experiment = idea["falsifiable_test"]
    baseline_block = "Blocked until the Fin-JEPA constrained baseline protocol is validated."
    return (
        _blocked_step(mechanism_step, baseline_block),
        _blocked_step(str(experiment["design"]), baseline_block),
        _blocked_step(
            "Evaluate primary metric: "
            + str(experiment["primary_metric"])
            + "; secondary metrics: "
            + ", ".join(str(metric) for metric in experiment["secondary_metrics"]),
            "Blocked until split equivalence and metric implementation are validated.",
        ),
        _blocked_step(
            "Apply rejection rule: " + str(experiment["failure_condition"]),
            "Blocked until the controlled comparison has execution evidence.",
        ),
    )


def _model(architecture: str, rationale: str, *source_refs: str) -> ModelRequirements:
    return ModelRequirements(
        architecture=proposed(architecture, rationale, *source_refs),
        code_availability=unknown(
            "No retained evidence establishes runnable code for this exact direction and protocol."
        ),
        checkpoint_availability=unknown(
            "No retained evidence establishes an equivalent checkpoint for this direction."
        ),
    )


def _data(
    time_horizon: EvidenceStatement,
    granularity: EvidenceStatement,
    context: str,
) -> DataRequirements:
    return DataRequirements(
        access=unknown(f"Data access for {context} has not been audited or obtained."),
        license=unknown(
            f"Dataset redistribution and research-use licensing for {context} are absent."
        ),
        splits=proposed(
            "Chronological purged walk-forward splits; fit preprocessing and labels on training "
            "only.",
            "Exact source splits are absent; this proposed split prevents temporal leakage.",
        ),
        time_horizon=time_horizon,
        granularity=granularity,
    )


def build_directions(
    results: dict[str, Any],
    prior_art: dict[str, Any],
) -> tuple[InvestigationDirection, ...]:
    ideas = {str(row["candidate_id"]): row for row in results["proposed_ideas"]}
    assessments = {str(row["source_idea_id"]): row for row in prior_art["candidate_assessments"]}
    return (
        _uncertainty_direction(ideas["JEPA-IDEA-01"], assessments["JEPA-IDEA-01"]),
        _event_direction(ideas["JEPA-IDEA-02"], assessments["JEPA-IDEA-02"]),
        _dual_target_direction(ideas["JEPA-IDEA-03"], assessments["JEPA-IDEA-03"]),
    )


def _objective(idea: dict[str, Any], assessment: dict[str, Any]) -> str:
    return f"{idea['mechanistic_bridge']} Remaining question: {assessment['remaining_question']}"


def _uncertainty_direction(
    idea: dict[str, Any], assessment: dict[str, Any]
) -> InvestigationDirection:
    return InvestigationDirection(
        title=str(idea["title"]),
        objective=_objective(idea, assessment),
        replication_steps=_experiment_steps(
            idea,
            "Implement a calibration comparator against the unchanged point Fin-JEPA baseline.",
        ),
        data=_data(
            reported("6,230 equities spanning 2010-2026.", CORE_REF),
            reported("Daily observations with 22 price-volume features.", CORE_REF),
            "Fin-JEPA equity and calibration comparison data",
        ),
        model=_model(
            "Keep the reported 64-latent, 367K-parameter Fin-JEPA point model as baseline; "
            "add a distributional output and a separately calibrated comparator.",
            "The point architecture is reported, while distributional prediction is proposed.",
            CORE_REF,
            CALIBRATION_REF,
        ),
        compute=unknown_compute(),
        assumptions=(
            reported(
                "Fin-JEPA reports latent MSE 0.2922 versus identity 0.3249, with downstream "
                "AUC about 0.49 and Spearman r about zero; these results were not rerun.",
                CORE_REF,
            ),
            *operational_assumptions(
                "Fit regime strata and calibration parameters inside each training fold only."
            ),
        ),
    )


def _event_direction(idea: dict[str, Any], assessment: dict[str, Any]) -> InvestigationDirection:
    return InvestigationDirection(
        title=str(idea["title"]),
        objective=_objective(idea, assessment),
        replication_steps=_experiment_steps(
            idea,
            "First reproduce CET's earnings-relevance and availability-timestamp baseline; then "
            "test the reported external gating mechanism only if that baseline is available.",
        ),
        data=_data(
            proposed(
                "Pre-register earnings event windows and availability timestamps before fusion.",
                "CET reports rapidly decaying earnings relevance, but the joint JEPA horizon is "
                "proposed.",
                CORE_REF,
                CET_REF,
            ),
            proposed(
                "Keep daily Fin-JEPA and next-minute CET baselines separate before aligning "
                "inputs.",
                "The sources report incompatible daily and minute granularities.",
                CORE_REF,
                CET_REF,
            ),
            "price-volume, earnings, and event-availability data",
        ),
        model=_model(
            "Compare price-only Fin-JEPA, CET-style earnings conditioning, unconditional fusion, "
            "and the externally reported causal relevance gate.",
            "CET is CPC rather than JEPA, and the gate comes from GS-FUSE; their integration is "
            "proposed.",
            CORE_REF,
            CET_REF,
            GATE_REF,
        ),
        compute=unknown_compute(),
        assumptions=operational_assumptions(
            "Reject any fold using earnings or exogenous values unavailable at the decision "
            "timestamp."
        ),
    )


def _dual_target_direction(
    idea: dict[str, Any], assessment: dict[str, Any]
) -> InvestigationDirection:
    return InvestigationDirection(
        title=str(idea["title"]),
        objective=_objective(idea, assessment),
        replication_steps=_experiment_steps(
            idea,
            "If this direction is selected, first reproduce the denoising mechanism and downstream "
            "SVM reference before introducing a dual target.",
        ),
        data=_data(
            proposed(
                "Begin with a daily-equity window comparable to Fin-JEPA; treat Bitcoin and "
                "limit-order extensions as separate follow-ups.",
                "The denoising source spans incompatible datasets and horizons.",
                CORE_REF,
                DENOISING_REF,
            ),
            proposed(
                "Use daily equity first; do not pool daily, one-minute, and limit-order "
                "observations.",
                "The denoising paper reports all three granularities, not a pooled protocol.",
                CORE_REF,
                DENOISING_REF,
            ),
            "raw and denoising-target financial data",
        ),
        model=_model(
            "Preserve the Fin-JEPA raw future-latent head and add a denoised market-state head "
            "only after reproducing the denoising autoencoder with its downstream SVM reference.",
            "The sources report these mechanisms separately; the dual-target architecture is "
            "proposed.",
            CORE_REF,
            DENOISING_REF,
        ),
        compute=unknown_compute(),
        assumptions=operational_assumptions(
            "Fit denoising transforms and target thresholds on training data only in every fold."
        ),
    )
