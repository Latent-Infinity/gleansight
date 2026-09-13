from __future__ import annotations

from papers.domain.investigation_plan import (
    EvidenceStatement,
    InvestigationDirection,
    InvestigationPlan,
    NumericEstimate,
    ReplicationStep,
)


def render_investigation_plan_markdown(plan: InvestigationPlan) -> str:
    lines = ["# Investigation Plan", "", f"**Question:** {plan.question}", "", "## Sources"]
    lines.extend(
        f"- `{source.paper_id}`: {source.title or 'Title unknown'}" for source in plan.sources
    )
    baseline = plan.baseline_replication
    lines.extend(
        [
            "",
            "## Baseline Replication",
            f"- Core paper: `{baseline.core_paper_ref}`",
            f"- Strategy: `{baseline.strategy.value}`",
            f"- Justification: {baseline.justification}",
            f"- Stop/advance rule: {baseline.stop_advance_rule}",
            "- Information completeness: "
            + (
                baseline.information_completeness.assessment.value
                if baseline.information_completeness.assessment is not None
                else "unknown"
            )
            + f" [{baseline.information_completeness.evidence_status.value}]",
            "- Missing information: "
            + (
                "; ".join(baseline.missing_information)
                if baseline.missing_information
                else "No missing items listed; completeness is supported above."
            ),
            _render_statement("Protocol equivalence", baseline.protocol_equivalence),
            _render_statement("Metric comparability", baseline.metric_comparability),
            f"- Comparison scope: `{baseline.comparison_scope.value}`",
            "- Deviations:",
        ]
    )
    lines.extend(_render_statement("Deviation", deviation) for deviation in baseline.deviations)
    lines.extend(
        [
            "- Success criteria: " + "; ".join(baseline.success_criteria),
            "- Steps:",
        ]
    )
    lines.extend(_render_step(step) for step in baseline.steps)
    lines.extend(["", "## Investigation Directions"])
    for direction in plan.directions:
        lines.extend(_render_direction(direction))
    return "\n".join(lines)


def _render_step(step: ReplicationStep) -> str:
    evidence = f"; evidence: {', '.join(step.evidence_refs)}" if step.evidence_refs else ""
    blocked = f"; blocked: {step.blocked_reason}" if step.blocked_reason else ""
    return f"  - [{step.status.value}] {step.description}{evidence}{blocked}"


def _render_statement(label: str, statement: EvidenceStatement) -> str:
    value = statement.value or "unknown"
    refs = ", ".join(statement.source_refs) or "none"
    rationale = statement.uncertainty_rationale or "none"
    return (
        f"- {label}: {value} [{statement.claim_kind.value}/{statement.evidence_status.value}; "
        f"sources: {refs}; uncertainty: {rationale}]"
    )


def _render_estimate(label: str, estimate: NumericEstimate) -> str:
    value = "unknown" if estimate.value is None else f"{estimate.value:g} {estimate.unit}"
    refs = ", ".join(estimate.source_refs) or "none"
    basis = estimate.basis or estimate.uncertainty_rationale or "unknown"
    return (
        f"- {label}: {value} [{estimate.claim_kind.value}/{estimate.evidence_status.value}; "
        f"basis: {basis}; sources: {refs}]"
    )


def _render_direction(direction: InvestigationDirection) -> list[str]:
    lines = ["", f"### {direction.title}", direction.objective, "", "Replication steps:"]
    lines.extend(_render_step(step) for step in direction.replication_steps)
    lines.append("\nData requirements:")
    lines.extend(
        _render_statement(label, value)
        for label, value in (
            ("Access", direction.data.access),
            ("License", direction.data.license),
            ("Splits", direction.data.splits),
            ("Time horizon", direction.data.time_horizon),
            ("Granularity", direction.data.granularity),
        )
    )
    lines.append("\nModel requirements:")
    lines.extend(
        _render_statement(label, value)
        for label, value in (
            ("Architecture", direction.model.architecture),
            ("Code availability", direction.model.code_availability),
            ("Checkpoint availability", direction.model.checkpoint_availability),
        )
    )
    lines.extend(
        [
            "\nCompute requirements:",
            f"- Feasibility tier: `{direction.compute.feasibility_tier.value}`",
            _render_statement("Hardware", direction.compute.hardware),
            _render_estimate("VRAM", direction.compute.vram_gb),
            _render_estimate("GPU hours", direction.compute.gpu_hours),
            "\nAssumptions:",
        ]
    )
    lines.extend(
        _render_statement("Assumption", assumption) for assumption in direction.assumptions
    )
    return lines
