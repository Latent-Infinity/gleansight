from __future__ import annotations

from typing import Any, Final

from papers.domain import (
    BaselineReplication,
    ComparisonScope,
    CompletenessAssessment,
    EvidenceStatus,
    InformationCompleteness,
    InvestigationPlan,
    ReplicationStep,
    ReplicationStrategy,
    SourceReference,
    StepStatus,
)
from scripts._jepa_investigation_directions import build_directions
from scripts._jepa_plan_values import proposed, unknown

PLAN_SOURCE_IDS: Final = (
    "N11-FIN-01",
    "arXiv:2507.05470",
    "N11-FIN-02",
    "arXiv:2605.28520",
    "N11-FIN-05",
)


def build_investigation_plan(
    results: dict[str, Any],
    ledger: dict[str, Any],
    prior_art: dict[str, Any],
) -> InvestigationPlan:
    source_titles = {
        **{str(row["record_id"]): str(row["title"]) for row in ledger["records"]},
        **{str(row["stable_id"]): str(row["title"]) for row in prior_art["primary_sources"]},
    }
    return InvestigationPlan(
        question=(
            "What must be reproduced from Fin-JEPA before testing calibrated uncertainty, "
            "event-conditioned relevance gating, or raw-plus-denoised dual targets?"
        ),
        sources=tuple(
            SourceReference(paper_id=source_id, title=source_titles[source_id])
            for source_id in PLAN_SOURCE_IDS
        ),
        baseline_replication=_baseline_replication(),
        directions=build_directions(results, prior_art),
    )


def _blocked_step(description: str, reason: str) -> ReplicationStep:
    return ReplicationStep(
        description=description,
        status=StepStatus.blocked,
        evidence_refs=(),
        blocked_reason=reason,
    )


def _baseline_replication() -> BaselineReplication:
    audit_dependency = (
        "Blocked until the source, code, data, and license audit resolves prerequisites."
    )
    return BaselineReplication(
        core_paper_ref="N11-FIN-01",
        strategy=ReplicationStrategy.constrained_reproduction,
        justification=(
            "Fin-JEPA is the only direct JEPA source. It reports 6,230 equities from 2010-2026, "
            "2.07M training samples, 22 price-volume features, 64-dimensional latents, 367K "
            "parameters, 30 context and 10 future steps, a four-layer causal Transformer, 50 "
            "epochs, and SIGReg 0.1. Exact replication is blocked by absent exact data "
            "construction, splits, feature definitions, optimizer, license, checkpoint, hardware, "
            "and runtime details; substitutions must be recorded and cannot support "
            "paper-equivalent numeric claims until equivalence is established. This constrained "
            "reproduction preserves the reported prediction objective and architecture targets; "
            "unlike conceptual reimplementation, it does not reduce the work to mechanism-only "
            "evidence. Exact replication remains a future target after equivalence is demonstrated."
        ),
        missing_information=(
            "Exact security universe construction and data access path",
            "Exact chronological split boundaries and preprocessing fit policy",
            "Definitions and transformations for all 22 price-volume features",
            "Optimizer, schedule, batch size, seeds, and stopping configuration",
            "Dataset and implementation licenses",
            "Runnable code revision and trained checkpoint availability",
            "Training hardware, VRAM, elapsed runtime, GPU-hours, storage, CPU, RAM, and budget",
        ),
        information_completeness=InformationCompleteness(
            evidence_status=EvidenceStatus.proposed,
            assessment=CompletenessAssessment.incomplete,
            source_refs=("N11-FIN-01",),
            uncertainty_rationale=(
                "The retained Fin-JEPA source supports the reported architecture and outcomes but "
                "does not supply the listed protocol, access, license, checkpoint, or compute "
                "details."
            ),
        ),
        protocol_equivalence=unknown(
            "Protocol equivalence is unestablished because exact features, splits, preprocessing, "
            "optimizer settings, seeds, code, and checkpoint are unavailable.",
            "N11-FIN-01",
        ),
        metric_comparability=unknown(
            "Metric comparability is unestablished until the reimplemented pipeline, data scope, "
            "and evaluation definitions are shown equivalent to the published protocol.",
            "N11-FIN-01",
        ),
        deviations=(
            proposed(
                "Use a reduced legally available equity panel instead of the reported 6,230-equity "
                "dataset for smoke and controlled reproduction runs.",
                "The reported source dataset access path and license are unavailable; the exact "
                "universe remains the future exact-replication target.",
                "N11-FIN-01",
            ),
            proposed(
                "Reimplement the reported 22-input, 30-context, 10-future, 64-latent structure "
                "while explicitly choosing and recording missing feature definitions, "
                "chronological splits, preprocessing, optimizer settings, and seeds.",
                "The retained source reports structural targets but omits an executable source "
                "protocol for these choices.",
                "N11-FIN-01",
            ),
            proposed(
                "Compare the reimplemented predictor only with an identity baseline under the same "
                "local protocol, with no direct comparison to published numeric results.",
                "Protocol equivalence and metric comparability remain unknown.",
                "N11-FIN-01",
            ),
        ),
        comparison_scope=ComparisonScope.no_direct_comparison,
        success_criteria=(
            "Audit records every substitution and establishes lawful data/code access.",
            "Smoke implementation reproduces tensor shapes for 30 context steps, 10 future steps, "
            "22 inputs, and 64-dimensional latents without claiming metric equivalence.",
            "Reduced-data controlled reproduction compares latent prediction with identity under "
            "one chronological leakage-controlled protocol.",
            "Paper-number comparison is allowed only after protocol equivalence is documented.",
        ),
        stop_advance_rule=(
            "Stop at audit if access, licensing, or timestamp-safe construction fails. Advance "
            "from smoke to reduced data only after shape and leakage checks pass; advance to full "
            "scale only after protocol validation and an observed hardware/resource budget."
        ),
        steps=(
            ReplicationStep(
                description=(
                    "Audit the source revision, executable code, checkpoint, data construction, "
                    "exact features and splits, optimizer, licenses, and reported-versus-absent "
                    "details."
                ),
                status=StepStatus.not_started,
                evidence_refs=(),
                blocked_reason=None,
            ),
            _blocked_step(
                "Build a smoke implementation of the reported 367K-parameter PriceEncoder and "
                "four-layer causal Transformer with SIGReg 0.1.",
                audit_dependency,
            ),
            _blocked_step(
                "Run a reduced legally available equity-panel controlled reproduction for 50 "
                "epochs only after recording all substitutions; compare latent MSE to identity "
                "only within that reproduction.",
                audit_dependency,
            ),
            _blocked_step(
                "Treat exact 6,230-equity replication as a future target using the original "
                "protocol, not as a direct comparison from the constrained reproduction.",
                "Blocked until protocol equivalence, metric comparability, lawful full-data "
                "access, and measured storage, CPU, RAM, VRAM, runtime, GPU-hour, and budget "
                "evidence exist.",
            ),
        ),
    )
