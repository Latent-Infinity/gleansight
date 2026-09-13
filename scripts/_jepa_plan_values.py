from __future__ import annotations

from papers.domain import (
    ClaimKind,
    ComputeFeasibilityTier,
    ComputeRequirements,
    EvidenceStatement,
    EvidenceStatus,
    NumericEstimate,
)


def reported(value: str, *source_refs: str) -> EvidenceStatement:
    return EvidenceStatement(
        claim_kind=ClaimKind.fact,
        evidence_status=EvidenceStatus.reported,
        value=value,
        source_refs=source_refs,
        uncertainty_rationale=None,
    )


def proposed(
    value: str,
    rationale: str,
    *source_refs: str,
) -> EvidenceStatement:
    return EvidenceStatement(
        claim_kind=ClaimKind.proposal,
        evidence_status=EvidenceStatus.proposed,
        value=value,
        source_refs=source_refs,
        uncertainty_rationale=rationale,
    )


def unknown(rationale: str, *source_refs: str) -> EvidenceStatement:
    return EvidenceStatement(
        claim_kind=ClaimKind.fact,
        evidence_status=EvidenceStatus.unknown,
        value=None,
        source_refs=source_refs,
        uncertainty_rationale=rationale,
    )


def unknown_compute() -> ComputeRequirements:
    profiling_gap = (
        "No retained source reports hardware, and the user's hardware has not been benchmarked."
    )
    return ComputeRequirements(
        feasibility_tier=ComputeFeasibilityTier.unknown,
        hardware=unknown(profiling_gap),
        vram_gb=NumericEstimate(
            claim_kind=ClaimKind.fact,
            evidence_status=EvidenceStatus.unknown,
            value=None,
            unit="GiB",
            basis=None,
            source_refs=(),
            uncertainty_rationale=(
                "VRAM is unknown until the audited implementation is profiled on a smoke batch."
            ),
        ),
        gpu_hours=NumericEstimate(
            claim_kind=ClaimKind.fact,
            evidence_status=EvidenceStatus.unknown,
            value=None,
            unit="GPU-hour",
            basis=None,
            source_refs=(),
            uncertainty_rationale=(
                "GPU-hours are unknown because no equivalent implementation or hardware run is "
                "profiled."
            ),
        ),
    )


def operational_assumptions(leakage_rule: str) -> tuple[EvidenceStatement, ...]:
    return (
        unknown("Storage capacity and retained dataset size in bytes are not reported."),
        unknown("CPU core count and host RAM requirements are not reported or profiled."),
        unknown("Elapsed runtime and monetary budget are unknown before smoke-tier profiling."),
        proposed(
            "Pin software and preprocessing dependencies after the source/code audit.",
            "Versions and optimizer details are absent, so dependencies cannot yet be equivalent.",
        ),
        proposed(
            leakage_rule, "This is a prospective control, not an executed or source-reported split."
        ),
    )
