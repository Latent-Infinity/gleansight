from __future__ import annotations

from typing import Any


def valid_investigation_plan_payload(
    question: str = "Which result should be replicated before adjacent mechanisms are tested?",
) -> dict[str, Any]:
    reported = {
        "claim_kind": "fact",
        "evidence_status": "reported",
        "value": "Public benchmark data",
        "source_refs": ["paper-1"],
        "uncertainty_rationale": None,
    }
    unknown = {
        "claim_kind": "fact",
        "evidence_status": "unknown",
        "value": None,
        "source_refs": [],
        "uncertainty_rationale": "The retrieved paper does not state this detail.",
    }
    return {
        "question": question,
        "sources": [{"paper_id": "paper-1", "title": "Core Paper"}],
        "baseline_replication": {
            "core_paper_ref": "paper-1",
            "strategy": "constrained_reproduction",
            "justification": "The original checkpoint is unavailable, but the method is specified.",
            "missing_information": ["Original random seeds"],
            "information_completeness": {
                "evidence_status": "unknown",
                "assessment": None,
                "source_refs": [],
                "uncertainty_rationale": "The retrieved corpus may omit implementation details.",
            },
            "protocol_equivalence": unknown,
            "metric_comparability": unknown,
            "deviations": [
                {
                    "claim_kind": "proposal",
                    "evidence_status": "proposed",
                    "value": (
                        "Use a reimplementation because the original checkpoint is unavailable."
                    ),
                    "source_refs": [],
                    "uncertainty_rationale": (
                        "Equivalence must be measured before direct comparison."
                    ),
                }
            ],
            "comparison_scope": "no_direct_comparison",
            "success_criteria": ["Metric is comparable under the documented split"],
            "stop_advance_rule": (
                "Stop if the baseline metric cannot be made comparable; advance only after it is."
            ),
            "steps": [
                {
                    "description": "Reproduce the core paper baseline on its documented split.",
                    "status": "not_started",
                    "evidence_refs": [],
                    "blocked_reason": None,
                }
            ],
        },
        "directions": [
            {
                "title": "Adjacent mechanism ablation",
                "objective": "Test one adjacent mechanism after the baseline is comparable.",
                "replication_steps": [
                    {
                        "description": "Run the baseline before changing the mechanism.",
                        "status": "not_started",
                        "evidence_refs": [],
                        "blocked_reason": None,
                    }
                ],
                "data": {
                    "access": reported,
                    "license": unknown,
                    "splits": reported,
                    "time_horizon": unknown,
                    "granularity": unknown,
                },
                "model": {
                    "architecture": reported,
                    "code_availability": unknown,
                    "checkpoint_availability": unknown,
                },
                "compute": {
                    "feasibility_tier": "unknown",
                    "hardware": unknown,
                    "vram_gb": {
                        "claim_kind": "fact",
                        "evidence_status": "unknown",
                        "value": None,
                        "unit": "GiB",
                        "basis": None,
                        "source_refs": [],
                        "uncertainty_rationale": "No hardware measurements are reported.",
                    },
                    "gpu_hours": {
                        "claim_kind": "proposal",
                        "evidence_status": "proposed",
                        "value": 8.0,
                        "unit": "GPU-hour",
                        "basis": "Assumes one pilot run on a single comparable GPU.",
                        "source_refs": [],
                        "uncertainty_rationale": (
                            "This is a planning estimate, not a paper-reported value."
                        ),
                    },
                },
                "assumptions": [
                    {
                        "claim_kind": "proposal",
                        "evidence_status": "proposed",
                        "value": "The evaluation metric can be implemented consistently.",
                        "source_refs": [],
                        "uncertainty_rationale": "This must be checked before execution.",
                    }
                ],
            }
        ],
    }
